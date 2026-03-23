from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

from context_use.proxy.handler import (
    ContextProxy,
    ContextProxyResult,
    ContextProxyStreamResult,
)
from context_use.proxy.headers import DEFAULT_PREFIX, ProxyHeaders

logger = logging.getLogger(__name__)

CONTENT_LENGTH_HEADER = "content-length"

_HOP_BY_HOP = frozenset(
    [
        b"connection",
        b"host",
        b"keep-alive",
        b"proxy-authenticate",
        b"proxy-authorization",
        b"te",
        b"trailers",
        b"transfer-encoding",
        b"upgrade",
    ]
)

_ALLOWED_UPSTREAM_HOSTS = frozenset(["api.openai.com"])

_DEFAULT_ENRICH_ENABLED = True

Message = dict[str, Any]
Scope = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def create_proxy_app(
    handler: ContextProxy,
    *,
    upstream_url: str | None = None,
    session_id: str | None = None,
    header_prefix: str = DEFAULT_PREFIX,
) -> ASGIApp:
    ctxuse_headers = ProxyHeaders.from_prefix(header_prefix)

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return

        client = scope.get("client")
        client_addr = f"{client[0]}:{client[1]}" if client else "-"
        http_version = scope.get("http_version", "1.1")
        logger.debug(
            '%s - "%s %s HTTP/%s"',
            client_addr,
            scope["method"],
            scope["path"],
            http_version,
        )

        raw = await _read_body(receive)
        headers_dict = {k.decode().lower(): v.decode() for k, v in scope["headers"]}

        upstream_host = headers_dict.get(ctxuse_headers.upstream_host)
        resolved_upstream_url, upstream_error = _resolve_upstream_url(
            upstream_url=upstream_url,
            upstream_host=upstream_host,
        )
        if upstream_error is not None:
            await _send_json(
                send, 400, _error_body(upstream_error, "invalid_request_error")
            )
            return

        resolved_session_id = headers_dict.get(ctxuse_headers.session_id) or session_id
        enrich_enabled = _parse_bool_header(
            headers_dict.get(ctxuse_headers.enrich_enabled),
            default=_DEFAULT_ENRICH_ENABLED,
        )

        forward_headers = [
            (k, v)
            for k, v in scope["headers"]
            if k.lower() not in _HOP_BY_HOP
            and k.lower() != CONTENT_LENGTH_HEADER.encode()
            and k.lower() != ctxuse_headers.session_id.encode()
            and k.lower() != ctxuse_headers.upstream_host.encode()
            and k.lower() != ctxuse_headers.enrich_enabled.encode()
        ]

        try:
            result = await handler.handle(
                scope["method"],
                scope["path"],
                forward_headers,
                raw,
                upstream_url=resolved_upstream_url,
                session_id=resolved_session_id,
                enrich_enabled=enrich_enabled,
            )
        except ValueError as exc:
            await _send_json(send, 400, _error_body(str(exc), "invalid_request_error"))
            return
        except Exception as exc:
            status = int(getattr(exc, "status_code", 500))
            logger.error("Proxy request failed: %s", exc)
            await _send_json(send, status, _error_body(str(exc), type(exc).__name__))
            return

        if isinstance(result, ContextProxyStreamResult):
            await _send_upstream_stream(send, result)
            return
        await _send_upstream_response(send, result)

    return app


def _resolve_upstream_url(
    *,
    upstream_url: str | None,
    upstream_host: str | None,
) -> tuple[str, str | None]:
    if upstream_url is not None:
        parsed = urlsplit(upstream_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return "", (
                "Invalid upstream URL. Use a full http:// or https:// URL, for "
                "example https://api.openai.com"
            )

        parsed_host = parsed.hostname
        if parsed_host is None:
            return "", (
                "Invalid upstream URL. Use a full http:// or https:// URL, for "
                "example https://api.openai.com"
            )

        allowed = ", ".join(sorted(_ALLOWED_UPSTREAM_HOSTS))
        if parsed_host.lower() not in _ALLOWED_UPSTREAM_HOSTS:
            return "", (
                f"Unknown upstream host {parsed_host!r} from --upstream-url. "
                f"Allowed hosts: {allowed}"
            )
        return upstream_url.rstrip("/"), None

    allowed = ", ".join(sorted(_ALLOWED_UPSTREAM_HOSTS))
    if not upstream_host:
        return "", (
            f"Missing upstream host header. Set it to your upstream "
            f"provider, or start the proxy with --upstream-url. "
            f"Allowed hosts: {allowed}"
        )

    if "://" in upstream_host:
        parsed = urlsplit(upstream_host)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return "", (
                f"Invalid upstream host {upstream_host!r}. Use a bare hostname "
                "like api.openai.com or a full URL like https://api.openai.com"
            )
        hostname = (parsed.hostname or "").lower()
        if hostname not in _ALLOWED_UPSTREAM_HOSTS:
            return "", (f"Unknown upstream host {hostname!r}. Allowed hosts: {allowed}")
        return upstream_host.rstrip("/"), None

    hostname = upstream_host.lower().split(":")[0]
    if hostname in _ALLOWED_UPSTREAM_HOSTS:
        return f"https://{upstream_host}", None

    return "", (f"Unknown upstream host {upstream_host!r}. Allowed hosts: {allowed}")


async def _read_body(receive: Receive) -> bytes:
    body = b""
    while True:
        message = await receive()
        body += message.get("body", b"")
        if not message.get("more_body", False):
            break
    return body


async def _send_json(send: Send, status: int, data: dict[str, Any]) -> None:
    encoded = json.dumps(data).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(encoded)).encode()],
            ],
        }
    )
    await send({"type": "http.response.body", "body": encoded})


async def _send_upstream_response(send: Send, result: ContextProxyResult) -> None:
    resp_headers = _filter_response_headers(result.headers)
    await send(
        {
            "type": "http.response.start",
            "status": result.status,
            "headers": resp_headers,
        }
    )
    await send({"type": "http.response.body", "body": result.body})


async def _send_upstream_stream(
    send: Send,
    result: ContextProxyStreamResult,
) -> None:
    resp_headers = _filter_response_headers(result.headers)
    await send(
        {
            "type": "http.response.start",
            "status": result.status,
            "headers": resp_headers,
        }
    )
    async for chunk in result.chunks:
        await send({"type": "http.response.body", "body": chunk, "more_body": True})
    await send({"type": "http.response.body", "body": b""})


def _filter_response_headers(
    headers: list[tuple[bytes, bytes]],
) -> list[tuple[bytes, bytes]]:
    return [(k, v) for k, v in headers if k.lower() not in _HOP_BY_HOP]


def _error_body(message: str, error_type: str) -> dict[str, Any]:
    return {"error": {"message": message, "type": error_type}}


def _parse_bool_header(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"false", "0", "no"}

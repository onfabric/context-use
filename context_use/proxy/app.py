from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from context_use.proxy.handler import (
    ContextProxy,
    ContextProxyResult,
    ContextProxyStreamResult,
)

logger = logging.getLogger(__name__)

SESSION_ID_HEADER = "ctxuse-session-id"
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

Message = dict[str, Any]
Scope = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def create_proxy_app(
    handler: ContextProxy,
    *,
    target_host: str | None = None,
) -> ASGIApp:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return

        raw = await _read_body(receive)
        headers_dict = {k.decode().lower(): v.decode() for k, v in scope["headers"]}

        host_error = _invalid_upstream_host_message(
            headers_dict, target_host=target_host
        )
        if host_error is not None:
            await _send_json(
                send, 400, _error_body(host_error, "invalid_request_error")
            )
            return

        host = target_host or headers_dict["host"]
        upstream_url = f"https://{host}"
        session_id = headers_dict.get(SESSION_ID_HEADER)

        # Hop-by-hop headers and the session-id header are connection-scoped or internal
        # and are not meant for the upstream provider.
        # content-length is also stripped and recomputed from the rewritten body
        forward_headers = [
            (k, v)
            for k, v in scope["headers"]
            if k.lower() not in _HOP_BY_HOP
            and k.lower() != CONTENT_LENGTH_HEADER.encode()
            and k.lower() != SESSION_ID_HEADER.encode()
        ]

        try:
            result = await handler.handle(
                scope["method"],
                scope["path"],
                forward_headers,
                raw,
                upstream_url=upstream_url,
                session_id=session_id,
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


def _invalid_upstream_host_message(
    headers: dict[str, str],
    *,
    target_host: str | None,
) -> str | None:
    host = target_host or headers.get("host")
    allowed = ", ".join(sorted(_ALLOWED_UPSTREAM_HOSTS))
    if not host:
        return (
            "Missing Host header. Set it to your upstream provider, or start the "
            f"proxy with --target. Allowed hosts: {allowed}"
        )

    hostname = host.lower().split(":")[0]
    if hostname in _ALLOWED_UPSTREAM_HOSTS:
        return None

    source = "--target" if target_host else "Host header"
    return f"Unknown upstream host {host!r} from {source}. Allowed hosts: {allowed}"


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

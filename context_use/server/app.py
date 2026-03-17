from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

import httpx

from context_use.proxy.handler import (
    ContextProxy,
    ContextProxyStreamResult,
    RouteNotFoundError,
)

logger = logging.getLogger(__name__)

SESSION_ID_HEADER = "ctxuse-session-id"

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

Message = dict[str, Any]
Scope = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def create_app(handler: ContextProxy, upstream_url: str) -> ASGIApp:
    upstream = upstream_url.rstrip("/")

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        if scope["method"] == "GET" and scope["path"] == "/health":
            await _send_json(send, 200, {"status": "ok"})
            return
        raw = await _read_body(receive)
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        api_key = _extract_api_key(headers.get("authorization", ""))
        session_id = headers.get(SESSION_ID_HEADER)
        try:
            result = await handler.handle(
                scope["method"],
                scope["path"],
                raw,
                api_key=api_key,
                session_id=session_id,
            )
        except RouteNotFoundError:
            # If a route is not found in ContextProxy, simply forward the request
            await _proxy_request(scope, send, upstream, raw)
            return
        except ValueError as exc:
            await _send_json(send, 400, _error_body(str(exc), "invalid_request_error"))
            return
        except Exception as exc:
            status = int(getattr(exc, "status_code", 500))
            logger.error("LLM forwarding failed: %s", exc)
            await _send_json(send, status, _error_body(str(exc), type(exc).__name__))
            return
        if isinstance(result, ContextProxyStreamResult):
            await _send_sse(send, result.chunks)
            return
        await _send_json(send, 200, result.data)

    return app


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


async def _send_sse(
    send: Send,
    chunks: AsyncGenerator[dict[str, Any], None],
) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"text/event-stream"],
                [b"cache-control", b"no-cache"],
            ],
        }
    )
    async for chunk in chunks:
        line = f"data: {json.dumps(chunk, default=str)}\n\n".encode()
        await send({"type": "http.response.body", "body": line, "more_body": True})
    await send({"type": "http.response.body", "body": b"data: [DONE]\n\n"})


def _make_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient()


async def _proxy_request(
    scope: Scope,
    send: Send,
    upstream: str,
    body: bytes,
) -> None:
    method: str = scope["method"]
    path: str = scope["path"]
    query: bytes = scope.get("query_string", b"")
    url = upstream + path + (f"?{query.decode()}" if query else "")

    forward_headers = [
        (k, v) for k, v in scope["headers"] if k.lower() not in _HOP_BY_HOP
    ]

    try:
        async with _make_http_client() as client:
            upstream_resp = await client.request(
                method=method,
                url=url,
                headers=forward_headers,
                content=body,
            )
    except Exception as exc:
        logger.error("Upstream proxy failed: %s", exc)
        await _send_json(send, 502, _error_body(str(exc), "upstream_error"))
        return

    resp_headers = [
        [k, v] for k, v in upstream_resp.headers.raw if k.lower() not in _HOP_BY_HOP
    ]
    await send(
        {
            "type": "http.response.start",
            "status": upstream_resp.status_code,
            "headers": resp_headers,
        }
    )
    await send({"type": "http.response.body", "body": upstream_resp.content})


def _extract_api_key(authorization: str) -> str | None:
    if authorization.startswith("Bearer "):
        key = authorization[7:].strip()
        return key or None
    return None


def _error_body(message: str, error_type: str) -> dict[str, Any]:
    return {"error": {"message": message, "type": error_type}}

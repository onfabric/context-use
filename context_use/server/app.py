from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from context_use.proxy.handler import ProxyHandler, ProxyStreamResult

logger = logging.getLogger(__name__)

SESSION_ID_HEADER = "ctxuse-session-id"


def create_app(handler: ProxyHandler) -> FastAPI:
    app = FastAPI(title="context-use proxy")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/chat/completions", response_model=None)
    async def chat_completions(request: Request) -> Response:
        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content=_error_body("Invalid JSON body", "invalid_request_error"),
            )

        if "model" not in body or "messages" not in body:
            return JSONResponse(
                status_code=400,
                content=_error_body(
                    "'model' and 'messages' are required",
                    "invalid_request_error",
                ),
            )

        api_key = _extract_api_key(request)
        session_id = request.headers.get(SESSION_ID_HEADER)

        try:
            result = await handler.chat_completion(
                body, api_key=api_key, session_id=session_id
            )
        except Exception as exc:
            status = int(getattr(exc, "status_code", 500))
            logger.error("LLM forwarding failed: %s", exc)
            return JSONResponse(
                status_code=status,
                content=_error_body(str(exc), type(exc).__name__),
            )

        if isinstance(result, ProxyStreamResult):
            return StreamingResponse(
                _sse_format(result.chunks),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache"},
            )
        return JSONResponse(content=result.data)

    return app


def _extract_api_key(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        key = auth[7:].strip()
        return key or None
    return None


async def _sse_format(
    chunks: AsyncGenerator[dict[str, Any], None],
) -> AsyncGenerator[str, None]:
    async for chunk in chunks:
        yield f"data: {json.dumps(chunk, default=str)}\n\n"
    yield "data: [DONE]\n\n"


def _error_body(message: str, error_type: str) -> dict[str, Any]:
    return {"error": {"message": message, "type": error_type}}

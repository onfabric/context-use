from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import litellm
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from context_use.facade.core import ContextUse
from context_use.proxy.enrichment import enrich_messages

logger = logging.getLogger(__name__)


def create_app(ctx: ContextUse, *, top_k: int = 5) -> FastAPI:
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

        logger.debug("Received request: %s", body)

        messages: list[dict[str, Any]] = body["messages"]
        stream: bool = body.get("stream", False)
        max_tokens = body.get("max_tokens")

        api_key = _extract_api_key(request)

        if _should_enrich(max_tokens):
            body["messages"] = await enrich_messages(messages, ctx, top_k=top_k)
        else:
            logger.debug("Skipping enrichment (max_tokens=%s)", max_tokens)

        if isinstance(max_tokens, int) and max_tokens < 2:
            body.pop("max_tokens")

        # litellm's per-provider allowlist may lag behind the actual API
        # surface, so drop unrecognised params instead of erroring.
        forward_kwargs: dict[str, Any] = {**body, "drop_params": True}
        if api_key:
            forward_kwargs["api_key"] = api_key

        try:
            response = await litellm.acompletion(**forward_kwargs)
            if stream:
                return StreamingResponse(
                    _stream_chunks(response),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache"},
                )
            else:
                return JSONResponse(content=response.model_dump())  # type: ignore[union-attr]
        except Exception as exc:
            status = int(getattr(exc, "status_code", 500))
            logger.error("LLM forwarding failed: %s", exc)
            return JSONResponse(
                status_code=status,
                content=_error_body(str(exc), type(exc).__name__),
            )

    return app


def _extract_api_key(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        key = auth[7:].strip()
        return key or None
    return None


async def _stream_chunks(response: Any) -> AsyncGenerator[str, None]:
    try:
        async for chunk in response:
            data = chunk.model_dump()
            yield f"data: {json.dumps(data, default=str)}\n\n"
    except Exception:
        logger.error("Streaming error", exc_info=True)
    yield "data: [DONE]\n\n"


_MIN_MAX_TOKENS_FOR_ENRICHMENT = 50


def _should_enrich(max_tokens: int | None) -> bool:
    if max_tokens is None:
        return True
    return max_tokens >= _MIN_MAX_TOKENS_FOR_ENRICHMENT


def _error_body(message: str, error_type: str) -> dict[str, Any]:
    return {"error": {"message": message, "type": error_type}}

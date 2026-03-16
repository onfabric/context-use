from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import litellm
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from context_use.facade.core import ContextUse
from context_use.proxy.enrichment import enrich_messages

if TYPE_CHECKING:
    from context_use.proxy.background import BackgroundMemoryProcessor

logger = logging.getLogger(__name__)


def create_app(
    ctx: ContextUse,
    processor: BackgroundMemoryProcessor,
) -> FastAPI:
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

        messages: list[dict[str, Any]] = body["messages"]
        stream: bool = body.get("stream", False)
        max_tokens = body.get("max_tokens")

        api_key = _extract_api_key(request)
        session_id = request.headers.get("x-session-id")
        should_process = _should_enrich(max_tokens)

        logger.info(
            "Request received: model=%s messages=%d session=%s stream=%s",
            body.get("model"),
            len(messages),
            session_id or "-",
            stream,
        )

        if _should_enrich(max_tokens):
            body["messages"] = await enrich_messages(messages, ctx)
        else:
            logger.debug("Skipping enrichment (max_tokens=%s)", max_tokens)

        # Some clients send max_tokens=1 as a connectivity probe; OpenAI
        # rejects that outright, so drop it and let the model use its default.
        if isinstance(max_tokens, int) and max_tokens < 2:
            body.pop("max_tokens")

        # litellm's per-provider allowlist may lag behind the actual API
        # surface, so drop unrecognised params instead of erroring.
        forward_kwargs: dict[str, Any] = {**body, "drop_params": True}
        if api_key:
            forward_kwargs["api_key"] = api_key

        try:
            logger.info("Response started: model=%s", body.get("model"))
            response = await litellm.acompletion(**forward_kwargs)
            if stream:
                return StreamingResponse(
                    _stream_and_process(
                        response,
                        messages=messages,
                        session_id=session_id,
                        processor=processor,
                        should_process=should_process,
                    ),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache"},
                )
            else:
                data: dict[str, Any] = response.model_dump()  # type: ignore[union-attr]
                logger.info("Response finished: model=%s", body.get("model"))
                if should_process:
                    assistant_text = _extract_assistant_text(data)
                    _schedule_processing(
                        processor,
                        messages,
                        assistant_text,
                        session_id=session_id,
                    )
                return JSONResponse(content=data)
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


async def _stream_and_process(
    response: Any,
    *,
    messages: list[dict[str, Any]],
    session_id: str | None,
    processor: BackgroundMemoryProcessor,
    should_process: bool,
) -> AsyncGenerator[str, None]:
    assistant_parts: list[str] = []
    chunk_count = 0
    try:
        async for chunk in response:
            data = chunk.model_dump()
            _accumulate_chunk(data, assistant_parts)
            if chunk_count == 0:
                logger.info("Response started (streaming)")
            chunk_count += 1
            yield f"data: {json.dumps(data, default=str)}\n\n"
    except Exception:
        logger.error("Streaming error", exc_info=True)
    yield "data: [DONE]\n\n"
    logger.info("Response finished (streaming): chunks=%d", chunk_count)

    if should_process:
        assistant_text = "".join(assistant_parts)
        _schedule_processing(processor, messages, assistant_text, session_id=session_id)


def _accumulate_chunk(data: dict[str, Any], parts: list[str]) -> None:
    choices = data.get("choices") or []
    for choice in choices:
        delta = choice.get("delta") or {}
        content = delta.get("content")
        if isinstance(content, str):
            parts.append(content)


def _extract_assistant_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        return message.get("content") or ""
    return ""


def _schedule_processing(
    processor: BackgroundMemoryProcessor,
    messages: list[dict[str, Any]],
    assistant_text: str,
    *,
    session_id: str | None,
) -> None:
    full_messages = [*messages, {"role": "assistant", "content": assistant_text}]
    processor.schedule(full_messages, session_id=session_id)


_MIN_MAX_TOKENS_FOR_ENRICHMENT = 50


def _should_enrich(max_tokens: int | None) -> bool:
    if max_tokens is None:
        return True
    return max_tokens >= _MIN_MAX_TOKENS_FOR_ENRICHMENT


def _error_body(message: str, error_type: str) -> dict[str, Any]:
    return {"error": {"message": message, "type": error_type}}

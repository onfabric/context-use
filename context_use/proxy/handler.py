from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import litellm

from context_use.proxy.enrichment import enrich_messages

if TYPE_CHECKING:
    from context_use.facade.core import ContextUse
    from context_use.proxy.background import BackgroundMemoryProcessor

logger = logging.getLogger(__name__)

_MIN_MAX_TOKENS_FOR_ENRICHMENT = 50


@dataclass(frozen=True, slots=True)
class ProxyResult:
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProxyStreamResult:
    chunks: AsyncGenerator[dict[str, Any], None]


class ProxyHandler:
    def __init__(
        self,
        ctx: ContextUse,
        processor: BackgroundMemoryProcessor,
    ) -> None:
        self._ctx = ctx
        self._processor = processor

    async def chat_completion(
        self,
        body: dict[str, Any],
        *,
        api_key: str | None = None,
        session_id: str | None = None,
    ) -> ProxyResult | ProxyStreamResult:
        messages: list[dict[str, Any]] = body["messages"]
        stream: bool = body.get("stream", False)
        max_tokens = body.get("max_tokens")
        should_process = _should_enrich(max_tokens)

        logger.info(
            "Request received: model=%s messages=%d session=%s stream=%s",
            body.get("model"),
            len(messages),
            session_id or "-",
            stream,
        )

        if should_process:
            body = {**body, "messages": await enrich_messages(messages, self._ctx)}
        else:
            logger.debug("Skipping enrichment (max_tokens=%s)", max_tokens)

        if isinstance(max_tokens, int) and max_tokens < 2:
            body = {k: v for k, v in body.items() if k != "max_tokens"}

        forward_kwargs: dict[str, Any] = {**body, "drop_params": True}
        if api_key:
            forward_kwargs["api_key"] = api_key

        logger.info("Response started: model=%s", body.get("model"))
        response = await litellm.acompletion(**forward_kwargs)

        if stream:
            return ProxyStreamResult(
                chunks=self._stream_chunks(
                    response,
                    messages=messages,
                    session_id=session_id,
                    should_process=should_process,
                ),
            )

        data: dict[str, Any] = response.model_dump()  # type: ignore[union-attr]
        logger.info("Response finished: model=%s", body.get("model"))
        if should_process:
            assistant_text = _extract_assistant_text(data)
            self._schedule(messages, assistant_text, session_id=session_id)
        return ProxyResult(data=data)

    async def _stream_chunks(
        self,
        response: Any,
        *,
        messages: list[dict[str, Any]],
        session_id: str | None,
        should_process: bool,
    ) -> AsyncGenerator[dict[str, Any], None]:
        assistant_parts: list[str] = []
        chunk_count = 0
        try:
            async for chunk in response:
                data = chunk.model_dump()
                _accumulate_chunk(data, assistant_parts)
                if chunk_count == 0:
                    logger.info("Response started (streaming)")
                chunk_count += 1
                yield data
        except Exception:
            logger.error("Streaming error", exc_info=True)
        logger.info("Response finished (streaming): chunks=%d", chunk_count)

        if should_process:
            assistant_text = "".join(assistant_parts)
            self._schedule(messages, assistant_text, session_id=session_id)

    def _schedule(
        self,
        messages: list[dict[str, Any]],
        assistant_text: str,
        *,
        session_id: str | None,
    ) -> None:
        full_messages = [*messages, {"role": "assistant", "content": assistant_text}]
        self._processor.schedule(full_messages, session_id=session_id)


def _should_enrich(max_tokens: int | None) -> bool:
    if max_tokens is None:
        return True
    return max_tokens >= _MIN_MAX_TOKENS_FOR_ENRICHMENT


def _extract_assistant_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        return message.get("content") or ""
    return ""


def _accumulate_chunk(data: dict[str, Any], parts: list[str]) -> None:
    choices = data.get("choices") or []
    for choice in choices:
        delta = choice.get("delta") or {}
        content = delta.get("content")
        if isinstance(content, str):
            parts.append(content)

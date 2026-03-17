from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from httpx import AsyncClient

from context_use.proxy.enrichment import enrich_messages

if TYPE_CHECKING:
    from context_use.facade.core import ContextUse
    from context_use.proxy.background import BackgroundMemoryProcessor

logger = logging.getLogger(__name__)

_MIN_MAX_TOKENS_FOR_ENRICHMENT = 50


@dataclass(frozen=True, slots=True)
class ContextProxyResult:
    status: int
    headers: list[tuple[bytes, bytes]]
    body: bytes


@dataclass(frozen=True, slots=True)
class ContextProxyStreamResult:
    status: int
    headers: list[tuple[bytes, bytes]]
    chunks: AsyncGenerator[bytes, None]


class ContextProxy:
    def __init__(
        self,
        ctx: ContextUse,
        processor: BackgroundMemoryProcessor,
    ) -> None:
        self._ctx = ctx
        self._processor = processor

    async def handle(
        self,
        method: str,
        path: str,
        headers: list[tuple[bytes, bytes]],
        body: bytes,
        *,
        upstream_url: str,
        session_id: str | None = None,
    ) -> ContextProxyResult | ContextProxyStreamResult:
        routes = {
            ("POST", "/v1/chat/completions"): self._chat_completion,
        }
        handler = routes.get((method.upper(), path))
        if handler is None:
            return await _forward_request(method, path, headers, body, upstream_url)
        try:
            parsed: dict[str, Any] = json.loads(body)
        except Exception:
            raise ValueError("Invalid JSON body") from None
        return await handler(
            parsed, headers=headers, upstream_url=upstream_url, session_id=session_id
        )

    async def _chat_completion(
        self,
        body: dict[str, Any],
        *,
        headers: list[tuple[bytes, bytes]],
        upstream_url: str,
        session_id: str | None = None,
    ) -> ContextProxyResult | ContextProxyStreamResult:
        if "model" not in body or "messages" not in body:
            raise ValueError("'model' and 'messages' are required")

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

        enriched_body = json.dumps(body).encode()
        url = upstream_url.rstrip("/") + "/v1/chat/completions"

        if stream:
            status, resp_headers, chunks = await _start_upstream_stream(
                url, headers, enriched_body
            )
            return ContextProxyStreamResult(
                status=status,
                headers=resp_headers,
                chunks=self._accumulate_and_schedule(
                    chunks,
                    messages=messages,
                    session_id=session_id,
                    should_process=should_process,
                ),
            )

        async with AsyncClient() as client:
            resp = await client.post(url, headers=headers, content=enriched_body)

        logger.info(
            "Response finished: model=%s status=%d", body.get("model"), resp.status_code
        )

        if should_process:
            try:
                assistant_text = _extract_assistant_text(resp.json())
            except Exception:
                assistant_text = ""
            if assistant_text:
                self._schedule(messages, assistant_text, session_id=session_id)

        return ContextProxyResult(
            status=resp.status_code,
            headers=list(resp.headers.raw),
            body=resp.content,
        )

    async def _accumulate_and_schedule(
        self,
        chunks: AsyncGenerator[bytes, None],
        *,
        messages: list[dict[str, Any]],
        session_id: str | None,
        should_process: bool,
    ) -> AsyncGenerator[bytes, None]:
        assistant_parts: list[str] = []
        chunk_count = 0
        try:
            async for chunk in chunks:
                if chunk_count == 0:
                    logger.info("Response started (streaming)")
                if should_process:
                    _accumulate_sse_bytes(chunk, assistant_parts)
                chunk_count += 1
                yield chunk
        except Exception:
            logger.error("Streaming error", exc_info=True)
        logger.info("Response finished (streaming): chunks=%d", chunk_count)

        if should_process:
            assistant_text = "".join(assistant_parts)
            if assistant_text:
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


async def _forward_request(
    method: str,
    path: str,
    headers: list[tuple[bytes, bytes]],
    body: bytes,
    upstream_url: str,
) -> ContextProxyResult:
    url = upstream_url.rstrip("/") + path
    async with AsyncClient() as client:
        resp = await client.request(
            method=method, url=url, headers=headers, content=body
        )
    return ContextProxyResult(
        status=resp.status_code,
        headers=list(resp.headers.raw),
        body=resp.content,
    )


async def _start_upstream_stream(
    url: str,
    headers: list[tuple[bytes, bytes]],
    body: bytes,
) -> tuple[int, list[tuple[bytes, bytes]], AsyncGenerator[bytes, None]]:
    stack = contextlib.AsyncExitStack()
    client = await stack.enter_async_context(AsyncClient())
    response = await stack.enter_async_context(
        client.stream("POST", url, headers=headers, content=body)
    )

    async def _iter_body() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await stack.aclose()

    return response.status_code, list(response.headers.raw), _iter_body()


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


def _accumulate_sse_bytes(raw: bytes, parts: list[str]) -> None:
    for line in raw.split(b"\n"):
        stripped = line.strip()
        if not stripped.startswith(b"data: "):
            continue
        data = stripped[6:]
        if data == b"[DONE]":
            continue
        try:
            parsed: dict[str, Any] = json.loads(data)
        except Exception:
            continue
        choices = parsed.get("choices") or []
        for choice in choices:
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if isinstance(content, str):
                parts.append(content)

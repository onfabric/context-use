from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from httpx import AsyncClient

from context_use.proxy.enrichment import enrich_messages, enrich_response_body

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
            ("POST", "/v1/responses"): self._response,
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

    async def _response(
        self,
        body: dict[str, Any],
        *,
        headers: list[tuple[bytes, bytes]],
        upstream_url: str,
        session_id: str | None = None,
    ) -> ContextProxyResult | ContextProxyStreamResult:
        if "model" not in body:
            raise ValueError("'model' is required")

        input_data: str | list[dict[str, Any]] = body.get("input", "")
        stream: bool = body.get("stream", False)
        max_output_tokens = body.get("max_output_tokens")
        should_process = _should_enrich(max_output_tokens)

        logger.info(
            "Response API request: model=%s session=%s stream=%s",
            body.get("model"),
            session_id or "-",
            stream,
        )

        if should_process:
            body = await enrich_response_body(body, self._ctx)
        else:
            logger.debug(
                "Skipping enrichment (max_output_tokens=%s)", max_output_tokens
            )

        if isinstance(max_output_tokens, int) and max_output_tokens < 2:
            body = {k: v for k, v in body.items() if k != "max_output_tokens"}

        enriched_body = json.dumps(body).encode()
        url = upstream_url.rstrip("/") + "/v1/responses"

        if stream:
            status, resp_headers, chunks = await _start_upstream_stream(
                url, headers, enriched_body
            )
            return ContextProxyStreamResult(
                status=status,
                headers=resp_headers,
                chunks=self._accumulate_response_and_schedule(
                    chunks,
                    input_data=input_data,
                    instructions=body.get("instructions"),
                    session_id=session_id,
                    should_process=should_process,
                ),
            )

        async with AsyncClient() as client:
            resp = await client.post(url, headers=headers, content=enriched_body)

        logger.info(
            "Response API finished: model=%s status=%d",
            body.get("model"),
            resp.status_code,
        )

        if should_process:
            try:
                assistant_text = _extract_response_output_text(resp.json())
            except Exception:
                assistant_text = ""
            if assistant_text:
                messages = _input_to_messages(input_data, body.get("instructions"))
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

    async def _accumulate_response_and_schedule(
        self,
        chunks: AsyncGenerator[bytes, None],
        *,
        input_data: str | list[dict[str, Any]],
        instructions: str | None,
        session_id: str | None,
        should_process: bool,
    ) -> AsyncGenerator[bytes, None]:
        assistant_parts: list[str] = []
        chunk_count = 0
        try:
            async for chunk in chunks:
                if chunk_count == 0:
                    logger.info("Response API started (streaming)")
                if should_process:
                    _accumulate_response_sse_bytes(chunk, assistant_parts)
                chunk_count += 1
                yield chunk
        except Exception:
            logger.error("Response API streaming error", exc_info=True)
        logger.info("Response API finished (streaming): chunks=%d", chunk_count)

        if should_process:
            assistant_text = "".join(assistant_parts)
            if assistant_text:
                messages = _input_to_messages(input_data, instructions)
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


def _extract_response_output_text(data: dict[str, Any]) -> str:
    output = data.get("output") or []
    texts: list[str] = []
    for item in output:
        if item.get("type") != "message":
            continue
        content = item.get("content") or []
        for part in content:
            if part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str):
                    texts.append(text)
    return " ".join(texts)


def _input_to_messages(
    input_data: str | list[dict[str, Any]],
    instructions: str | None = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if instructions:
        messages.append({"role": "system", "content": instructions})

    if isinstance(input_data, str):
        if input_data:
            messages.append({"role": "user", "content": input_data})
        return messages

    for item in input_data:
        role = item.get("role")
        if role == "developer":
            role = "system"
        if role not in ("user", "assistant", "system"):
            continue
        content = item.get("content")
        text: str | None = None
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = [
                part["text"]
                for part in content
                if isinstance(part, dict)
                and part.get("type") in ("input_text", "text", "output_text")
            ]
            text = " ".join(parts) if parts else None
        if text:
            messages.append({"role": role, "content": text})

    return messages


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


def _accumulate_response_sse_bytes(raw: bytes, parts: list[str]) -> None:
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
        if parsed.get("type") == "response.output_text.delta":
            delta = parsed.get("delta")
            if isinstance(delta, str):
                parts.append(delta)

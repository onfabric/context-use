from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from httpx import AsyncClient, Timeout

from context_use.proxy.enrichment import enrich_body
from context_use.proxy.log import log_request, log_response

if TYPE_CHECKING:
    from context_use.facade.core import ContextUse

logger = logging.getLogger(__name__)

_MIN_MAX_TOKENS_FOR_ENRICHMENT = 50
_UPSTREAM_TIMEOUT = Timeout(None)


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


type PostResponseCallback = Callable[
    [ContextUse, list[dict[str, Any]], str | None], None
]
"""Called after a proxied response completes with the ``ContextUse`` instance,
the full conversation (including the assistant reply), and the session ID.

Messages and session ID are JSON-serializable, so the callback can dispatch
to an async task runner, a Celery queue, or any other backend.

Example::

    def my_callback(
        ctx: ContextUse, messages: list[dict[str, Any]], session_id: str | None
    ) -> None:
        import asyncio
        print(f"[{session_id}] {len(messages)} messages")
        asyncio.create_task(
            ctx.generate_memories_from_messages(messages, session_id=session_id),
        )

    proxy = ContextProxy(ctx, post_response_callback=my_callback)
"""


class ContextProxy:
    def __init__(
        self,
        ctx: ContextUse,
        *,
        post_response_callback: PostResponseCallback | None = None,
    ) -> None:
        self._ctx = ctx
        self._client = AsyncClient(timeout=_UPSTREAM_TIMEOUT)
        self._post_response_callback = post_response_callback

    async def aclose(self) -> None:
        await self._client.aclose()

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
            return await _forward_request(
                self._client, method, path, headers, body, upstream_url
            )
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
        return await self._proxy_request(
            body,
            headers=headers,
            upstream_url=upstream_url,
            session_id=session_id,
            path="/v1/chat/completions",
            max_tokens_key="max_tokens",
            extract_text=_extract_assistant_text,
            sse_extract=_completion_sse_deltas,
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
        return await self._proxy_request(
            body,
            headers=headers,
            upstream_url=upstream_url,
            session_id=session_id,
            path="/v1/responses",
            max_tokens_key="max_output_tokens",
            extract_text=_extract_response_output_text,
            sse_extract=_response_sse_deltas,
        )

    async def _proxy_request(
        self,
        body: dict[str, Any],
        *,
        headers: list[tuple[bytes, bytes]],
        upstream_url: str,
        session_id: str | None,
        path: str,
        max_tokens_key: str,
        extract_text: Callable[[dict[str, Any]], str],
        sse_extract: Callable[[dict[str, Any]], list[str]],
    ) -> ContextProxyResult | ContextProxyStreamResult:
        stream: bool = body.get("stream", False)
        max_tokens = body.get(max_tokens_key)
        should_process = _should_enrich(max_tokens)
        scheduling_messages = _body_to_messages(body)

        log_request(
            "POST",
            path,
            model=body.get("model"),
            session_id=session_id,
            stream=stream,
        )

        if should_process:
            body = await enrich_body(body, self._ctx)
        else:
            logger.debug("Skipping enrichment (%s=%s)", max_tokens_key, max_tokens)

        if isinstance(max_tokens, int) and max_tokens < 2:
            body = {k: v for k, v in body.items() if k != max_tokens_key}

        enriched_body = json.dumps(body).encode()
        url = upstream_url.rstrip("/") + path

        if stream:
            status, resp_headers, chunks = await _start_upstream_stream(
                self._client, url, headers, enriched_body
            )
            return ContextProxyStreamResult(
                status=status,
                headers=resp_headers,
                chunks=self._stream_and_schedule(
                    chunks,
                    status=status,
                    sse_extract=sse_extract,
                    messages=scheduling_messages,
                    session_id=session_id,
                    should_process=should_process,
                ),
            )

        resp = await self._client.post(url, headers=headers, content=enriched_body)

        log_response(resp.status_code)

        if should_process:
            try:
                assistant_text = extract_text(resp.json())
            except Exception:
                assistant_text = ""
            if assistant_text:
                self._schedule(
                    scheduling_messages,
                    assistant_text,
                    session_id=session_id,
                )

        return ContextProxyResult(
            status=resp.status_code,
            headers=list(resp.headers.raw),
            body=resp.content,
        )

    async def _stream_and_schedule(
        self,
        chunks: AsyncGenerator[bytes, None],
        *,
        status: int,
        sse_extract: Callable[[dict[str, Any]], list[str]],
        messages: list[dict[str, Any]],
        session_id: str | None,
        should_process: bool,
    ) -> AsyncGenerator[bytes, None]:
        assistant_parts: list[str] = []
        chunk_count = 0
        try:
            async for chunk in chunks:
                if should_process:
                    _accumulate_sse_text(chunk, assistant_parts, sse_extract)
                chunk_count += 1
                yield chunk
        except Exception:
            logger.error("Streaming error", exc_info=True)
        log_response(status, chunks=chunk_count)

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
        if self._post_response_callback is None:
            return
        full_messages = [*messages, {"role": "assistant", "content": assistant_text}]
        self._post_response_callback(self._ctx, full_messages, session_id)


async def _forward_request(
    client: AsyncClient,
    method: str,
    path: str,
    headers: list[tuple[bytes, bytes]],
    body: bytes,
    upstream_url: str,
) -> ContextProxyResult:
    url = upstream_url.rstrip("/") + path
    resp = await client.request(method=method, url=url, headers=headers, content=body)
    return ContextProxyResult(
        status=resp.status_code,
        headers=list(resp.headers.raw),
        body=resp.content,
    )


async def _start_upstream_stream(
    client: AsyncClient,
    url: str,
    headers: list[tuple[bytes, bytes]],
    body: bytes,
) -> tuple[int, list[tuple[bytes, bytes]], AsyncGenerator[bytes, None]]:
    response = await client.send(
        client.build_request("POST", url, headers=headers, content=body),
        stream=True,
    )

    async def _iter_body() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await response.aclose()

    return response.status_code, list(response.headers.raw), _iter_body()


def _should_enrich(max_tokens: int | None) -> bool:
    if max_tokens is None:
        return True
    return max_tokens >= _MIN_MAX_TOKENS_FOR_ENRICHMENT


def _body_to_messages(body: dict[str, Any]) -> list[dict[str, Any]]:
    if "messages" in body:
        return body["messages"]
    return _input_to_messages(body.get("input", ""), body.get("instructions"))


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


def _accumulate_sse_text(
    raw: bytes,
    parts: list[str],
    extract: Callable[[dict[str, Any]], list[str]],
) -> None:
    for line in raw.split(b"\n"):
        stripped = line.strip()
        if not stripped.startswith(b"data: "):
            continue
        payload = stripped[6:]
        if payload == b"[DONE]":
            continue
        try:
            parsed: dict[str, Any] = json.loads(payload)
        except Exception:
            continue
        parts.extend(extract(parsed))


def _completion_sse_deltas(parsed: dict[str, Any]) -> list[str]:
    deltas: list[str] = []
    for choice in parsed.get("choices") or []:
        content = (choice.get("delta") or {}).get("content")
        if isinstance(content, str):
            deltas.append(content)
    return deltas


def _response_sse_deltas(parsed: dict[str, Any]) -> list[str]:
    if parsed.get("type") == "response.output_text.delta":
        delta = parsed.get("delta")
        if isinstance(delta, str):
            return [delta]
    return []

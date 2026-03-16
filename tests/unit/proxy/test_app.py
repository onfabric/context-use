from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from httpx import ASGITransport

from context_use.proxy.app import create_app
from context_use.proxy.background import BackgroundMemoryProcessor
from context_use.store.base import MemorySearchResult


def _mock_ctx(
    memories: list[MemorySearchResult] | None = None,
) -> AsyncMock:
    ctx = AsyncMock()
    ctx.search_memories.return_value = memories or []
    return ctx


def _mock_processor() -> MagicMock:
    processor = MagicMock(spec=BackgroundMemoryProcessor)
    processor.schedule = MagicMock()
    return processor


def _make_result() -> MemorySearchResult:
    return MemorySearchResult(
        id="mem-1",
        content="Likes pizza",
        from_date=date(2024, 1, 1),
        to_date=date(2024, 1, 15),
        similarity=0.95,
    )


def _completion_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": "openai/gpt-4o",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    body.update(overrides)
    return body


def _mock_model_response() -> MagicMock:
    resp = MagicMock()
    resp.model_dump.return_value = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hi there!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }
    return resp


class TestHealth:
    async def test_health(self) -> None:
        app = create_app(_mock_ctx(), _mock_processor())
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestChatCompletions:
    @patch("context_use.proxy.app.litellm")
    async def test_non_streaming(self, mock_litellm: MagicMock) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        ctx = _mock_ctx(memories=[_make_result()])
        app = create_app(ctx, _mock_processor())
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["choices"][0]["message"]["content"] == "Hi there!"

        call_kwargs = mock_litellm.acompletion.call_args
        forwarded_messages = call_kwargs.kwargs.get(
            "messages", call_kwargs.args[0] if call_kwargs.args else None
        )
        if forwarded_messages is None:
            forwarded_messages = call_kwargs[1]["messages"]
        assert any(
            "Likes pizza" in str(m.get("content", "")) for m in forwarded_messages
        )

    @patch("context_use.proxy.app.litellm")
    async def test_streaming(self, mock_litellm: MagicMock) -> None:
        chunk = MagicMock()
        chunk.model_dump.return_value = {
            "id": "chatcmpl-123",
            "object": "chat.completion.chunk",
            "created": 1700000000,
            "model": "gpt-4o",
            "choices": [
                {"index": 0, "delta": {"content": "Hi"}, "finish_reason": None}
            ],
        }

        async def mock_stream() -> Any:
            yield chunk

        mock_litellm.acompletion = AsyncMock(return_value=mock_stream())
        app = create_app(_mock_ctx(), _mock_processor())
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(stream=True),
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        lines = resp.text.strip().split("\n")
        data_lines = [line for line in lines if line.startswith("data: ")]
        assert len(data_lines) >= 2
        assert data_lines[-1] == "data: [DONE]"
        parsed = json.loads(data_lines[0].removeprefix("data: "))
        assert parsed["choices"][0]["delta"]["content"] == "Hi"

    async def test_missing_model(self) -> None:
        app = create_app(_mock_ctx(), _mock_processor())
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )
        assert resp.status_code == 400
        assert "required" in resp.json()["error"]["message"]

    async def test_missing_messages(self) -> None:
        app = create_app(_mock_ctx(), _mock_processor())
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4o"},
            )
        assert resp.status_code == 400

    @patch("context_use.proxy.app.litellm")
    async def test_forwards_api_key(self, mock_litellm: MagicMock) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        app = create_app(_mock_ctx(), _mock_processor())
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={"Authorization": "Bearer sk-test-key-123"},
            )

        assert resp.status_code == 200
        call_kwargs = mock_litellm.acompletion.call_args
        assert call_kwargs.kwargs.get("api_key") == "sk-test-key-123"

    @patch("context_use.proxy.app.litellm")
    async def test_llm_error_returns_error_response(
        self, mock_litellm: MagicMock
    ) -> None:
        exc = Exception("Rate limit exceeded")
        exc.status_code = 429  # type: ignore[attr-defined]
        mock_litellm.acompletion = AsyncMock(side_effect=exc)
        app = create_app(_mock_ctx(), _mock_processor())
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
            )

        assert resp.status_code == 429
        assert "Rate limit" in resp.json()["error"]["message"]

    @patch("context_use.proxy.app.litellm")
    async def test_enrichment_injects_memories(self, mock_litellm: MagicMock) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        ctx = _mock_ctx(memories=[_make_result()])
        app = create_app(ctx, _mock_processor())
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
            )

        ctx.search_memories.assert_awaited_once_with(query="Hello", top_k=5)

    @patch("context_use.proxy.app.litellm")
    async def test_passthrough_extra_params(self, mock_litellm: MagicMock) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        app = create_app(_mock_ctx(), _mock_processor())
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(temperature=0.7, max_tokens=100),
            )

        call_kwargs = mock_litellm.acompletion.call_args.kwargs
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 100

    @patch("context_use.proxy.app.litellm")
    async def test_skips_enrichment_for_low_max_tokens(
        self, mock_litellm: MagicMock
    ) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        ctx = _mock_ctx(memories=[_make_result()])
        app = create_app(ctx, _mock_processor())
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(max_tokens=1),
            )

        ctx.search_memories.assert_not_awaited()
        call_kwargs = mock_litellm.acompletion.call_args.kwargs
        forwarded = call_kwargs["messages"]
        assert not any("Likes pizza" in str(m.get("content", "")) for m in forwarded)
        assert "max_tokens" not in call_kwargs

    @patch("context_use.proxy.app.litellm")
    async def test_enriches_when_max_tokens_sufficient(
        self, mock_litellm: MagicMock
    ) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        ctx = _mock_ctx(memories=[_make_result()])
        app = create_app(ctx, _mock_processor())
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(max_tokens=200),
            )

        ctx.search_memories.assert_awaited_once()
        forwarded = mock_litellm.acompletion.call_args.kwargs["messages"]
        assert any("Likes pizza" in str(m.get("content", "")) for m in forwarded)


class TestBackgroundProcessing:
    @patch("context_use.proxy.app.litellm")
    async def test_non_streaming_schedules_processing(
        self, mock_litellm: MagicMock
    ) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        processor = _mock_processor()
        app = create_app(_mock_ctx(), processor)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
            )

        assert resp.status_code == 200
        processor.schedule.assert_called_once()
        messages = processor.schedule.call_args.args[0]
        assert any(m["role"] == "assistant" for m in messages)
        assert any(
            m.get("content") == "Hi there!"
            for m in messages
            if m["role"] == "assistant"
        )

    @patch("context_use.proxy.app.litellm")
    async def test_streaming_schedules_processing(
        self, mock_litellm: MagicMock
    ) -> None:
        chunk1 = MagicMock()
        chunk1.model_dump.return_value = {
            "id": "chatcmpl-123",
            "object": "chat.completion.chunk",
            "created": 1700000000,
            "model": "gpt-4o",
            "choices": [
                {"index": 0, "delta": {"content": "Hi"}, "finish_reason": None}
            ],
        }
        chunk2 = MagicMock()
        chunk2.model_dump.return_value = {
            "id": "chatcmpl-123",
            "object": "chat.completion.chunk",
            "created": 1700000000,
            "model": "gpt-4o",
            "choices": [
                {"index": 0, "delta": {"content": " there"}, "finish_reason": "stop"}
            ],
        }

        async def mock_stream() -> Any:
            yield chunk1
            yield chunk2

        mock_litellm.acompletion = AsyncMock(return_value=mock_stream())
        processor = _mock_processor()
        app = create_app(_mock_ctx(), processor)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(stream=True),
            )

        assert resp.status_code == 200
        processor.schedule.assert_called_once()
        messages = processor.schedule.call_args.args[0]
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0]["content"] == "Hi there"

    @patch("context_use.proxy.app.litellm")
    async def test_session_id_header_passed_through(
        self, mock_litellm: MagicMock
    ) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        processor = _mock_processor()
        app = create_app(_mock_ctx(), processor)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={"X-Session-Id": "sess-abc"},
            )

        processor.schedule.assert_called_once()
        assert processor.schedule.call_args.kwargs["session_id"] == "sess-abc"

    @patch("context_use.proxy.app.litellm")
    async def test_skips_processing_for_probe_requests(
        self, mock_litellm: MagicMock
    ) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        processor = _mock_processor()
        app = create_app(_mock_ctx(), processor)
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(max_tokens=1),
            )

        processor.schedule.assert_not_called()

from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from context_use.proxy.handler import (
    ContextProxy,
    ContextProxyResult,
    ContextProxyStreamResult,
    RouteNotFoundError,
    _should_enrich,
)
from context_use.store.base import MemorySearchResult


def _mock_ctx(
    memories: list[MemorySearchResult] | None = None,
) -> AsyncMock:
    ctx = AsyncMock()
    ctx.search_memories.return_value = memories or []
    return ctx


def _mock_processor() -> MagicMock:
    from context_use.proxy.background import BackgroundMemoryProcessor

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


class TestShouldEnrich:
    def test_none_returns_true(self) -> None:
        assert _should_enrich(None) is True

    def test_high_value_returns_true(self) -> None:
        assert _should_enrich(200) is True

    def test_threshold_returns_true(self) -> None:
        assert _should_enrich(50) is True

    def test_low_value_returns_false(self) -> None:
        assert _should_enrich(1) is False

    def test_below_threshold_returns_false(self) -> None:
        assert _should_enrich(49) is False


class TestChatCompletion:
    @patch("context_use.proxy.handler.litellm")
    async def test_non_streaming_returns_proxy_result(
        self, mock_litellm: MagicMock
    ) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        result = await handler._chat_completion(_completion_body())

        assert isinstance(result, ContextProxyResult)
        assert result.data["choices"][0]["message"]["content"] == "Hi there!"

    @patch("context_use.proxy.handler.litellm")
    async def test_streaming_returns_stream_result(
        self, mock_litellm: MagicMock
    ) -> None:
        chunk = MagicMock()
        chunk.model_dump.return_value = {
            "id": "chatcmpl-123",
            "object": "chat.completion.chunk",
            "choices": [
                {"index": 0, "delta": {"content": "Hi"}, "finish_reason": None}
            ],
        }

        async def mock_stream() -> Any:
            yield chunk

        mock_litellm.acompletion = AsyncMock(return_value=mock_stream())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        result = await handler._chat_completion(_completion_body(stream=True))

        assert isinstance(result, ContextProxyStreamResult)
        chunks = [c async for c in result.chunks]
        assert len(chunks) == 1
        assert chunks[0]["choices"][0]["delta"]["content"] == "Hi"

    @patch("context_use.proxy.handler.litellm")
    async def test_enriches_messages(self, mock_litellm: MagicMock) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        ctx = _mock_ctx(memories=[_make_result()])
        handler = ContextProxy(ctx, _mock_processor())

        await handler._chat_completion(_completion_body())

        ctx.search_memories.assert_awaited_once_with(query="Hello", top_k=5)
        forwarded = mock_litellm.acompletion.call_args.kwargs["messages"]
        assert any("Likes pizza" in str(m.get("content", "")) for m in forwarded)

    @patch("context_use.proxy.handler.litellm")
    async def test_skips_enrichment_for_low_max_tokens(
        self, mock_litellm: MagicMock
    ) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        ctx = _mock_ctx(memories=[_make_result()])
        handler = ContextProxy(ctx, _mock_processor())

        await handler._chat_completion(_completion_body(max_tokens=1))

        ctx.search_memories.assert_not_awaited()
        assert "max_tokens" not in mock_litellm.acompletion.call_args.kwargs

    @patch("context_use.proxy.handler.litellm")
    async def test_enriches_when_max_tokens_sufficient(
        self, mock_litellm: MagicMock
    ) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        ctx = _mock_ctx(memories=[_make_result()])
        handler = ContextProxy(ctx, _mock_processor())

        await handler._chat_completion(_completion_body(max_tokens=200))

        ctx.search_memories.assert_awaited_once()
        forwarded = mock_litellm.acompletion.call_args.kwargs["messages"]
        assert any("Likes pizza" in str(m.get("content", "")) for m in forwarded)

    @patch("context_use.proxy.handler.litellm")
    async def test_forwards_api_key(self, mock_litellm: MagicMock) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        await handler._chat_completion(_completion_body(), api_key="sk-test-123")

        assert mock_litellm.acompletion.call_args.kwargs["api_key"] == "sk-test-123"

    @patch("context_use.proxy.handler.litellm")
    async def test_passes_extra_params(self, mock_litellm: MagicMock) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        await handler._chat_completion(
            _completion_body(temperature=0.7, max_tokens=100)
        )

        call_kwargs = mock_litellm.acompletion.call_args.kwargs
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 100

    @patch("context_use.proxy.handler.litellm")
    async def test_sets_drop_params(self, mock_litellm: MagicMock) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        await handler._chat_completion(_completion_body())

        assert mock_litellm.acompletion.call_args.kwargs["drop_params"] is True

    @patch("context_use.proxy.handler.litellm")
    async def test_propagates_litellm_exceptions(self, mock_litellm: MagicMock) -> None:
        exc = Exception("Rate limit exceeded")
        exc.status_code = 429  # type: ignore[attr-defined]
        mock_litellm.acompletion = AsyncMock(side_effect=exc)
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        with pytest.raises(Exception, match="Rate limit exceeded"):
            await handler._chat_completion(_completion_body())


def _completion_bytes(**overrides: Any) -> bytes:
    return json.dumps(_completion_body(**overrides)).encode()


class TestHandle:
    @patch("context_use.proxy.handler.litellm")
    async def test_routes_post_chat_completions(self, mock_litellm: MagicMock) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        result = await handler.handle("POST", "/v1/chat/completions", _completion_bytes())

        assert isinstance(result, ContextProxyResult)

    @patch("context_use.proxy.handler.litellm")
    async def test_handle_is_case_insensitive_on_method(
        self, mock_litellm: MagicMock
    ) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        result = await handler.handle("post", "/v1/chat/completions", _completion_bytes())

        assert isinstance(result, ContextProxyResult)

    async def test_raises_route_not_found_for_unknown_path(self) -> None:
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        with pytest.raises(RouteNotFoundError):
            await handler.handle("POST", "/v1/unknown", _completion_bytes())

    async def test_raises_route_not_found_for_wrong_method(self) -> None:
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        with pytest.raises(RouteNotFoundError):
            await handler.handle("GET", "/v1/chat/completions", _completion_bytes())

    async def test_raises_value_error_on_invalid_json(self) -> None:
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        with pytest.raises(ValueError, match="Invalid JSON"):
            await handler.handle("POST", "/v1/chat/completions", b"not json")

    async def test_raises_value_error_on_missing_model(self) -> None:
        handler = ContextProxy(_mock_ctx(), _mock_processor())
        body = json.dumps({"messages": [{"role": "user", "content": "Hi"}]}).encode()

        with pytest.raises(ValueError, match="required"):
            await handler.handle("POST", "/v1/chat/completions", body)

    async def test_raises_value_error_on_missing_messages(self) -> None:
        handler = ContextProxy(_mock_ctx(), _mock_processor())
        body = json.dumps({"model": "gpt-4o"}).encode()

        with pytest.raises(ValueError, match="required"):
            await handler.handle("POST", "/v1/chat/completions", body)

    @patch("context_use.proxy.handler.litellm")
    async def test_forwards_api_key_and_session_id(
        self, mock_litellm: MagicMock
    ) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler.handle(
            "POST",
            "/v1/chat/completions",
            _completion_bytes(),
            api_key="sk-test",
            session_id="sess-xyz",
        )

        assert mock_litellm.acompletion.call_args.kwargs["api_key"] == "sk-test"
        assert processor.schedule.call_args.kwargs["session_id"] == "sess-xyz"


class TestBackgroundScheduling:
    @patch("context_use.proxy.handler.litellm")
    async def test_non_streaming_schedules_processing(
        self, mock_litellm: MagicMock
    ) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler._chat_completion(_completion_body())

        processor.schedule.assert_called_once()
        messages = processor.schedule.call_args.args[0]
        assert any(m["role"] == "assistant" for m in messages)
        assert any(
            m.get("content") == "Hi there!"
            for m in messages
            if m["role"] == "assistant"
        )

    @patch("context_use.proxy.handler.litellm")
    async def test_streaming_schedules_processing(
        self, mock_litellm: MagicMock
    ) -> None:
        chunk1 = MagicMock()
        chunk1.model_dump.return_value = {
            "choices": [
                {"index": 0, "delta": {"content": "Hi"}, "finish_reason": None}
            ],
        }
        chunk2 = MagicMock()
        chunk2.model_dump.return_value = {
            "choices": [
                {"index": 0, "delta": {"content": " there"}, "finish_reason": "stop"}
            ],
        }

        async def mock_stream() -> Any:
            yield chunk1
            yield chunk2

        mock_litellm.acompletion = AsyncMock(return_value=mock_stream())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        result = await handler._chat_completion(_completion_body(stream=True))
        assert isinstance(result, ContextProxyStreamResult)
        async for _ in result.chunks:
            pass

        processor.schedule.assert_called_once()
        messages = processor.schedule.call_args.args[0]
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0]["content"] == "Hi there"

    @patch("context_use.proxy.handler.litellm")
    async def test_session_id_forwarded(self, mock_litellm: MagicMock) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler._chat_completion(_completion_body(), session_id="sess-abc")

        assert processor.schedule.call_args.kwargs["session_id"] == "sess-abc"

    @patch("context_use.proxy.handler.litellm")
    async def test_skips_processing_for_probe(self, mock_litellm: MagicMock) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler._chat_completion(_completion_body(max_tokens=1))

        processor.schedule.assert_not_called()

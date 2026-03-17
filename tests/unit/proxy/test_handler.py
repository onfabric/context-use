from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from context_use.proxy.handler import (
    ContextProxy,
    ContextProxyResult,
    ContextProxyStreamResult,
    _accumulate_response_sse_bytes,
    _accumulate_sse_bytes,
    _extract_response_output_text,
    _input_to_messages,
    _should_enrich,
)
from context_use.store.base import MemorySearchResult


async def _aiter(*items: bytes) -> AsyncGenerator[bytes, None]:
    for item in items:
        yield item


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
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    body.update(overrides)
    return body


def _completion_bytes(**overrides: Any) -> bytes:
    return json.dumps(_completion_body(**overrides)).encode()


def _default_headers() -> list[tuple[bytes, bytes]]:
    return [
        (b"authorization", b"Bearer sk-test"),
        (b"content-type", b"application/json"),
    ]


def _mock_http_response(
    status: int = 200,
    headers: list[tuple[bytes, bytes]] | None = None,
    content: bytes | None = None,
) -> MagicMock:
    if content is None:
        content = json.dumps(
            {"choices": [{"message": {"role": "assistant", "content": "Hi there!"}}]}
        ).encode()
    resp = MagicMock()
    resp.status_code = status
    resp.headers.raw = headers or [(b"content-type", b"application/json")]
    resp.content = content
    resp.json = MagicMock(return_value=json.loads(content))
    return resp


def _setup_non_streaming_client(mock_cls: MagicMock, response: MagicMock) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_client


def _mock_streaming_response(
    status: int = 200,
    headers: list[tuple[bytes, bytes]] | None = None,
    chunks: list[bytes] | None = None,
) -> AsyncMock:
    resp = AsyncMock()
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = None
    resp.status_code = status
    resp.headers.raw = headers or [(b"content-type", b"text/event-stream")]
    _chunks = chunks or []
    resp.aiter_bytes = MagicMock(return_value=_aiter(*_chunks))
    return resp


def _setup_streaming_client(mock_cls: MagicMock, response: AsyncMock) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=response)
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_client


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


class TestAccumulateSseBytes:
    def test_extracts_content_delta(self) -> None:
        parts: list[str] = []
        raw = b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        _accumulate_sse_bytes(raw, parts)
        assert parts == ["Hello"]

    def test_ignores_done_sentinel(self) -> None:
        parts: list[str] = []
        raw = b"data: [DONE]\n\n"
        _accumulate_sse_bytes(raw, parts)
        assert parts == []

    def test_ignores_non_data_lines(self) -> None:
        parts: list[str] = []
        raw = b'event: message\ndata: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
        _accumulate_sse_bytes(raw, parts)
        assert parts == ["Hi"]

    def test_ignores_invalid_json(self) -> None:
        parts: list[str] = []
        raw = b"data: not json\n\n"
        _accumulate_sse_bytes(raw, parts)
        assert parts == []

    def test_handles_multiple_chunks_in_one_raw(self) -> None:
        parts: list[str] = []
        raw = (
            b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":" there"}}]}\n\n'
        )
        _accumulate_sse_bytes(raw, parts)
        assert parts == ["Hi", " there"]

    def test_skips_delta_without_content(self) -> None:
        parts: list[str] = []
        raw = b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
        _accumulate_sse_bytes(raw, parts)
        assert parts == []


class TestChatCompletion:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_non_streaming_returns_proxy_result(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        result = await handler._chat_completion(
            _completion_body(),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        assert isinstance(result, ContextProxyResult)
        assert result.status == 200
        assert b"Hi there!" in result.body

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_streaming_returns_stream_result(self, MockClient: MagicMock) -> None:
        chunk = b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
        _setup_streaming_client(MockClient, _mock_streaming_response(chunks=[chunk]))
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        result = await handler._chat_completion(
            _completion_body(stream=True),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        assert isinstance(result, ContextProxyStreamResult)
        assert result.status == 200
        chunks = [c async for c in result.chunks]
        assert len(chunks) == 1
        assert chunks[0] == chunk

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_enriches_messages(self, MockClient: MagicMock) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        ctx = _mock_ctx(memories=[_make_result()])
        handler = ContextProxy(ctx, _mock_processor())

        await handler._chat_completion(
            _completion_body(),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        ctx.search_memories.assert_awaited_once_with(query="Hello", top_k=5)
        sent_body = json.loads(mock_client.post.call_args.kwargs["content"])
        assert any(
            "Likes pizza" in str(m.get("content", "")) for m in sent_body["messages"]
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_skips_enrichment_for_low_max_tokens(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        ctx = _mock_ctx(memories=[_make_result()])
        handler = ContextProxy(ctx, _mock_processor())

        await handler._chat_completion(
            _completion_body(max_tokens=1),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        ctx.search_memories.assert_not_awaited()

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_strips_max_tokens_below_two(self, MockClient: MagicMock) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        await handler._chat_completion(
            _completion_body(max_tokens=1),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        sent_body = json.loads(mock_client.post.call_args.kwargs["content"])
        assert "max_tokens" not in sent_body

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_enriches_when_max_tokens_sufficient(
        self, MockClient: MagicMock
    ) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        ctx = _mock_ctx(memories=[_make_result()])
        handler = ContextProxy(ctx, _mock_processor())

        await handler._chat_completion(
            _completion_body(max_tokens=200),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        ctx.search_memories.assert_awaited_once()
        sent_body = json.loads(mock_client.post.call_args.kwargs["content"])
        assert any(
            "Likes pizza" in str(m.get("content", "")) for m in sent_body["messages"]
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_forwards_extra_params_in_body(self, MockClient: MagicMock) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        await handler._chat_completion(
            _completion_body(temperature=0.7, max_tokens=100),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        sent_body = json.loads(mock_client.post.call_args.kwargs["content"])
        assert sent_body["temperature"] == 0.7
        assert sent_body["max_tokens"] == 100

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_forwards_headers_to_upstream(self, MockClient: MagicMock) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        headers = [(b"authorization", b"Bearer sk-provider-key")]
        await handler._chat_completion(
            _completion_body(),
            headers=headers,
            upstream_url="https://api.openai.com",
        )

        assert mock_client.post.call_args.kwargs["headers"] == headers

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_posts_to_correct_url(self, MockClient: MagicMock) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        await handler._chat_completion(
            _completion_body(),
            headers=_default_headers(),
            upstream_url="https://api.anthropic.com",
        )

        assert (
            mock_client.post.call_args.args[0]
            == "https://api.anthropic.com/v1/chat/completions"
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_propagates_upstream_exceptions(self, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        with pytest.raises(Exception, match="connection refused"):
            await handler._chat_completion(
                _completion_body(),
                headers=_default_headers(),
                upstream_url="https://api.openai.com",
            )


class TestHandle:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_routes_post_chat_completions(self, MockClient: MagicMock) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        result = await handler.handle(
            "POST",
            "/v1/chat/completions",
            _default_headers(),
            _completion_bytes(),
            upstream_url="https://api.openai.com",
        )

        assert isinstance(result, ContextProxyResult)

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_handle_is_case_insensitive_on_method(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        result = await handler.handle(
            "post",
            "/v1/chat/completions",
            _default_headers(),
            _completion_bytes(),
            upstream_url="https://api.openai.com",
        )

        assert isinstance(result, ContextProxyResult)

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_unknown_path_forwarded_transparently(
        self, MockClient: MagicMock
    ) -> None:
        upstream_response = _mock_http_response(content=b'{"object":"list","data":[]}')
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=upstream_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        result = await handler.handle(
            "GET",
            "/v1/models",
            _default_headers(),
            b"",
            upstream_url="https://api.openai.com",
        )

        assert isinstance(result, ContextProxyResult)
        assert result.status == 200
        call = mock_client.request.call_args
        assert call.kwargs["method"] == "GET"
        assert call.kwargs["url"] == "https://api.openai.com/v1/models"

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_wrong_method_for_known_path_forwarded_transparently(
        self, MockClient: MagicMock
    ) -> None:
        upstream_response = _mock_http_response(content=b"{}")
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=upstream_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        result = await handler.handle(
            "GET",
            "/v1/chat/completions",
            _default_headers(),
            b"",
            upstream_url="https://api.openai.com",
        )

        assert isinstance(result, ContextProxyResult)
        call = mock_client.request.call_args
        assert call.kwargs["method"] == "GET"

    async def test_raises_value_error_on_invalid_json(self) -> None:
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        with pytest.raises(ValueError, match="Invalid JSON"):
            await handler.handle(
                "POST",
                "/v1/chat/completions",
                _default_headers(),
                b"not json",
                upstream_url="https://api.openai.com",
            )

    async def test_raises_value_error_on_missing_model(self) -> None:
        handler = ContextProxy(_mock_ctx(), _mock_processor())
        body = json.dumps({"messages": [{"role": "user", "content": "Hi"}]}).encode()

        with pytest.raises(ValueError, match="required"):
            await handler.handle(
                "POST",
                "/v1/chat/completions",
                _default_headers(),
                body,
                upstream_url="https://api.openai.com",
            )

    async def test_raises_value_error_on_missing_messages(self) -> None:
        handler = ContextProxy(_mock_ctx(), _mock_processor())
        body = json.dumps({"model": "gpt-4o"}).encode()

        with pytest.raises(ValueError, match="required"):
            await handler.handle(
                "POST",
                "/v1/chat/completions",
                _default_headers(),
                body,
                upstream_url="https://api.openai.com",
            )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_session_id_forwarded_to_scheduler(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler.handle(
            "POST",
            "/v1/chat/completions",
            _default_headers(),
            _completion_bytes(),
            upstream_url="https://api.openai.com",
            session_id="sess-xyz",
        )

        assert processor.schedule.call_args.kwargs["session_id"] == "sess-xyz"


class TestBackgroundScheduling:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_non_streaming_schedules_processing(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler._chat_completion(
            _completion_body(),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        processor.schedule.assert_called_once()
        messages = processor.schedule.call_args.args[0]
        assert any(m["role"] == "assistant" for m in messages)
        assert any(
            m.get("content") == "Hi there!"
            for m in messages
            if m["role"] == "assistant"
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_streaming_schedules_processing(self, MockClient: MagicMock) -> None:
        chunk1 = (
            b'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}\n\n'
        )
        chunk2 = (
            b'data: {"choices":[{"delta":{"content":" there"},"finish_reason":"stop"}]}'
            b"\n\ndata: [DONE]\n\n"
        )
        _setup_streaming_client(
            MockClient, _mock_streaming_response(chunks=[chunk1, chunk2])
        )
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        result = await handler._chat_completion(
            _completion_body(stream=True),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )
        assert isinstance(result, ContextProxyStreamResult)
        async for _ in result.chunks:
            pass

        processor.schedule.assert_called_once()
        messages = processor.schedule.call_args.args[0]
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0]["content"] == "Hi there"

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_session_id_forwarded(self, MockClient: MagicMock) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler._chat_completion(
            _completion_body(),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
            session_id="sess-abc",
        )

        assert processor.schedule.call_args.kwargs["session_id"] == "sess-abc"

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_skips_processing_for_probe(self, MockClient: MagicMock) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler._chat_completion(
            _completion_body(max_tokens=1),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        processor.schedule.assert_not_called()

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_skips_scheduling_when_assistant_text_empty(
        self, MockClient: MagicMock
    ) -> None:
        error_content = json.dumps({"error": {"message": "Invalid API key"}}).encode()
        _setup_non_streaming_client(
            MockClient,
            _mock_http_response(status=401, content=error_content),
        )
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler._chat_completion(
            _completion_body(),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        processor.schedule.assert_not_called()


def _response_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": "gpt-4o",
        "input": "Hello",
    }
    body.update(overrides)
    return body


def _response_bytes(**overrides: Any) -> bytes:
    return json.dumps(_response_body(**overrides)).encode()


def _mock_response_api_http_response(
    status: int = 200,
    headers: list[tuple[bytes, bytes]] | None = None,
    content: bytes | None = None,
) -> MagicMock:
    if content is None:
        content = json.dumps(
            {
                "id": "resp_123",
                "object": "response",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Hi there!",
                            }
                        ],
                    }
                ],
            }
        ).encode()
    resp = MagicMock()
    resp.status_code = status
    resp.headers.raw = headers or [(b"content-type", b"application/json")]
    resp.content = content
    resp.json = MagicMock(return_value=json.loads(content))
    return resp


class TestExtractResponseOutputText:
    def test_extracts_output_text(self) -> None:
        data = {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Hello!"}],
                }
            ]
        }
        assert _extract_response_output_text(data) == "Hello!"

    def test_extracts_multiple_output_texts(self) -> None:
        data = {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "Part 1"},
                        {"type": "output_text", "text": "Part 2"},
                    ],
                }
            ]
        }
        assert _extract_response_output_text(data) == "Part 1 Part 2"

    def test_skips_non_message_items(self) -> None:
        data = {
            "output": [
                {"type": "function_call", "name": "search"},
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Result"}],
                },
            ]
        }
        assert _extract_response_output_text(data) == "Result"

    def test_empty_output(self) -> None:
        assert _extract_response_output_text({"output": []}) == ""

    def test_no_output_key(self) -> None:
        assert _extract_response_output_text({}) == ""

    def test_skips_non_text_content(self) -> None:
        data = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "refusal", "refusal": "Cannot do that"}],
                }
            ]
        }
        assert _extract_response_output_text(data) == ""


class TestInputToMessages:
    def test_string_input(self) -> None:
        result = _input_to_messages("Hello")
        assert result == [{"role": "user", "content": "Hello"}]

    def test_string_input_with_instructions(self) -> None:
        result = _input_to_messages("Hello", "Be helpful")
        assert result == [
            {"role": "system", "content": "Be helpful"},
            {"role": "user", "content": "Hello"},
        ]

    def test_empty_string(self) -> None:
        result = _input_to_messages("")
        assert result == []

    def test_empty_string_with_instructions(self) -> None:
        result = _input_to_messages("", "Be helpful")
        assert result == [{"role": "system", "content": "Be helpful"}]

    def test_array_with_string_content(self) -> None:
        items: list[dict[str, Any]] = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        result = _input_to_messages(items)
        assert result == [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

    def test_array_with_input_text_content(self) -> None:
        items: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "Hello"}],
            }
        ]
        result = _input_to_messages(items)
        assert result == [{"role": "user", "content": "Hello"}]

    def test_developer_role_mapped_to_system(self) -> None:
        items: list[dict[str, Any]] = [{"role": "developer", "content": "Instructions"}]
        result = _input_to_messages(items)
        assert result == [{"role": "system", "content": "Instructions"}]

    def test_skips_unknown_roles(self) -> None:
        items: list[dict[str, Any]] = [
            {"role": "tool", "content": "result"},
            {"role": "user", "content": "Hello"},
        ]
        result = _input_to_messages(items)
        assert result == [{"role": "user", "content": "Hello"}]

    def test_empty_array(self) -> None:
        assert _input_to_messages([]) == []

    def test_skips_empty_content(self) -> None:
        items: list[dict[str, Any]] = [{"role": "user", "content": ""}]
        result = _input_to_messages(items)
        assert result == []


class TestAccumulateResponseSseBytes:
    def test_extracts_text_delta(self) -> None:
        parts: list[str] = []
        raw = (
            b"event: response.output_text.delta\n"
            b'data: {"type":"response.output_text.delta",'
            b'"delta":"Hello"}\n\n'
        )
        _accumulate_response_sse_bytes(raw, parts)
        assert parts == ["Hello"]

    def test_ignores_non_delta_events(self) -> None:
        parts: list[str] = []
        raw = (
            b"event: response.created\n"
            b'data: {"type":"response.created","response":{}}\n\n'
        )
        _accumulate_response_sse_bytes(raw, parts)
        assert parts == []

    def test_ignores_done_sentinel(self) -> None:
        parts: list[str] = []
        raw = b"data: [DONE]\n\n"
        _accumulate_response_sse_bytes(raw, parts)
        assert parts == []

    def test_ignores_invalid_json(self) -> None:
        parts: list[str] = []
        raw = b"data: not json\n\n"
        _accumulate_response_sse_bytes(raw, parts)
        assert parts == []

    def test_handles_multiple_deltas(self) -> None:
        parts: list[str] = []
        raw = (
            b'data: {"type":"response.output_text.delta","delta":"Hi"}\n\n'
            b'data: {"type":"response.output_text.delta","delta":" there"}\n\n'
        )
        _accumulate_response_sse_bytes(raw, parts)
        assert parts == ["Hi", " there"]

    def test_ignores_completed_event(self) -> None:
        parts: list[str] = []
        raw = b'data: {"type":"response.completed","response":{"id":"resp_123"}}\n\n'
        _accumulate_response_sse_bytes(raw, parts)
        assert parts == []


class TestResponseHandler:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_non_streaming_returns_proxy_result(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_response_api_http_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        result = await handler._response(
            _response_body(),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        assert isinstance(result, ContextProxyResult)
        assert result.status == 200
        assert b"Hi there!" in result.body

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_streaming_returns_stream_result(self, MockClient: MagicMock) -> None:
        chunk = (
            b"event: response.output_text.delta\n"
            b'data: {"type":"response.output_text.delta",'
            b'"delta":"Hi"}\n\n'
        )
        _setup_streaming_client(MockClient, _mock_streaming_response(chunks=[chunk]))
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        result = await handler._response(
            _response_body(stream=True),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        assert isinstance(result, ContextProxyStreamResult)
        assert result.status == 200
        chunks = [c async for c in result.chunks]
        assert len(chunks) == 1
        assert chunks[0] == chunk

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_enriches_with_memories(self, MockClient: MagicMock) -> None:
        mock_client = _setup_non_streaming_client(
            MockClient, _mock_response_api_http_response()
        )
        ctx = _mock_ctx(memories=[_make_result()])
        handler = ContextProxy(ctx, _mock_processor())

        await handler._response(
            _response_body(),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        ctx.search_memories.assert_awaited_once_with(query="Hello", top_k=5)
        sent_body = json.loads(mock_client.post.call_args.kwargs["content"])
        assert "Likes pizza" in sent_body["instructions"]

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_enriches_appends_to_existing_instructions(
        self, MockClient: MagicMock
    ) -> None:
        mock_client = _setup_non_streaming_client(
            MockClient, _mock_response_api_http_response()
        )
        ctx = _mock_ctx(memories=[_make_result()])
        handler = ContextProxy(ctx, _mock_processor())

        await handler._response(
            _response_body(instructions="Be helpful"),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        sent_body = json.loads(mock_client.post.call_args.kwargs["content"])
        assert sent_body["instructions"].startswith("Be helpful\n\n")
        assert "Likes pizza" in sent_body["instructions"]

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_skips_enrichment_for_low_max_output_tokens(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_response_api_http_response())
        ctx = _mock_ctx(memories=[_make_result()])
        handler = ContextProxy(ctx, _mock_processor())

        await handler._response(
            _response_body(max_output_tokens=1),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        ctx.search_memories.assert_not_awaited()

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_strips_max_output_tokens_below_two(
        self, MockClient: MagicMock
    ) -> None:
        mock_client = _setup_non_streaming_client(
            MockClient, _mock_response_api_http_response()
        )
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        await handler._response(
            _response_body(max_output_tokens=1),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        sent_body = json.loads(mock_client.post.call_args.kwargs["content"])
        assert "max_output_tokens" not in sent_body

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_posts_to_correct_url(self, MockClient: MagicMock) -> None:
        mock_client = _setup_non_streaming_client(
            MockClient, _mock_response_api_http_response()
        )
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        await handler._response(
            _response_body(),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        assert (
            mock_client.post.call_args.args[0] == "https://api.openai.com/v1/responses"
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_forwards_headers_to_upstream(self, MockClient: MagicMock) -> None:
        mock_client = _setup_non_streaming_client(
            MockClient, _mock_response_api_http_response()
        )
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        headers = [(b"authorization", b"Bearer sk-provider-key")]
        await handler._response(
            _response_body(),
            headers=headers,
            upstream_url="https://api.openai.com",
        )

        assert mock_client.post.call_args.kwargs["headers"] == headers

    async def test_raises_value_error_on_missing_model(self) -> None:
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        with pytest.raises(ValueError, match="required"):
            await handler._response(
                {"input": "Hello"},
                headers=_default_headers(),
                upstream_url="https://api.openai.com",
            )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_handles_array_input(self, MockClient: MagicMock) -> None:
        _setup_non_streaming_client(MockClient, _mock_response_api_http_response())
        ctx = _mock_ctx(memories=[_make_result()])
        handler = ContextProxy(ctx, _mock_processor())

        await handler._response(
            _response_body(
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "What food do I like?"}
                        ],
                    }
                ]
            ),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        ctx.search_memories.assert_awaited_once_with(
            query="What food do I like?", top_k=5
        )


class TestResponseHandleRouting:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_routes_post_responses(self, MockClient: MagicMock) -> None:
        _setup_non_streaming_client(MockClient, _mock_response_api_http_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        result = await handler.handle(
            "POST",
            "/v1/responses",
            _default_headers(),
            _response_bytes(),
            upstream_url="https://api.openai.com",
        )

        assert isinstance(result, ContextProxyResult)

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_handle_is_case_insensitive_on_method(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_response_api_http_response())
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        result = await handler.handle(
            "post",
            "/v1/responses",
            _default_headers(),
            _response_bytes(),
            upstream_url="https://api.openai.com",
        )

        assert isinstance(result, ContextProxyResult)

    async def test_raises_value_error_on_invalid_json(self) -> None:
        handler = ContextProxy(_mock_ctx(), _mock_processor())

        with pytest.raises(ValueError, match="Invalid JSON"):
            await handler.handle(
                "POST",
                "/v1/responses",
                _default_headers(),
                b"not json",
                upstream_url="https://api.openai.com",
            )

    async def test_raises_value_error_on_missing_model(self) -> None:
        handler = ContextProxy(_mock_ctx(), _mock_processor())
        body = json.dumps({"input": "Hello"}).encode()

        with pytest.raises(ValueError, match="required"):
            await handler.handle(
                "POST",
                "/v1/responses",
                _default_headers(),
                body,
                upstream_url="https://api.openai.com",
            )


class TestResponseBackgroundScheduling:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_non_streaming_schedules_processing(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_response_api_http_response())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler._response(
            _response_body(),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        processor.schedule.assert_called_once()
        messages = processor.schedule.call_args.args[0]
        assert any(m["role"] == "assistant" for m in messages)
        assert any(
            m.get("content") == "Hi there!"
            for m in messages
            if m["role"] == "assistant"
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_non_streaming_includes_input_in_messages(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_response_api_http_response())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler._response(
            _response_body(input="What is AI?"),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        messages = processor.schedule.call_args.args[0]
        assert any(
            m["role"] == "user" and m["content"] == "What is AI?" for m in messages
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_non_streaming_includes_instructions_as_system(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_response_api_http_response())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler._response(
            _response_body(instructions="Be helpful"),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        messages = processor.schedule.call_args.args[0]
        assert messages[0] == {"role": "system", "content": "Be helpful"}

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_streaming_schedules_processing(self, MockClient: MagicMock) -> None:
        chunk1 = b'data: {"type":"response.output_text.delta","delta":"Hi"}\n\n'
        chunk2 = (
            b'data: {"type":"response.output_text.delta",'
            b'"delta":" there"}\n\n'
            b'data: {"type":"response.completed",'
            b'"response":{}}\n\n'
        )
        _setup_streaming_client(
            MockClient, _mock_streaming_response(chunks=[chunk1, chunk2])
        )
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        result = await handler._response(
            _response_body(stream=True),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )
        assert isinstance(result, ContextProxyStreamResult)
        async for _ in result.chunks:
            pass

        processor.schedule.assert_called_once()
        messages = processor.schedule.call_args.args[0]
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0]["content"] == "Hi there"

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_session_id_forwarded(self, MockClient: MagicMock) -> None:
        _setup_non_streaming_client(MockClient, _mock_response_api_http_response())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler._response(
            _response_body(),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
            session_id="sess-abc",
        )

        assert processor.schedule.call_args.kwargs["session_id"] == "sess-abc"

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_skips_processing_for_probe(self, MockClient: MagicMock) -> None:
        _setup_non_streaming_client(MockClient, _mock_response_api_http_response())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler._response(
            _response_body(max_output_tokens=1),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        processor.schedule.assert_not_called()

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_skips_scheduling_when_output_text_empty(
        self, MockClient: MagicMock
    ) -> None:
        error_content = json.dumps({"error": {"message": "Invalid API key"}}).encode()
        _setup_non_streaming_client(
            MockClient,
            _mock_response_api_http_response(status=401, content=error_content),
        )
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)

        await handler._response(
            _response_body(),
            headers=_default_headers(),
            upstream_url="https://api.openai.com",
        )

        processor.schedule.assert_not_called()

from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from httpx import ASGITransport

from context_use.proxy.background import BackgroundMemoryProcessor
from context_use.proxy.handler import ProxyHandler
from context_use.server.app import create_app
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


def _make_handler(
    memories: list[MemorySearchResult] | None = None,
) -> ProxyHandler:
    return ProxyHandler(_mock_ctx(memories), _mock_processor())


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
        app = create_app(_make_handler(), upstream_url="https://api.openai.com")
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestRequestValidation:
    async def test_missing_model(self) -> None:
        app = create_app(_make_handler(), upstream_url="https://api.openai.com")
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
        app = create_app(_make_handler(), upstream_url="https://api.openai.com")
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4o"},
            )
        assert resp.status_code == 400

    async def test_invalid_json(self) -> None:
        app = create_app(_make_handler(), upstream_url="https://api.openai.com")
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                content=b"not json",
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 400
        assert "Invalid JSON" in resp.json()["error"]["message"]


class TestNonStreaming:
    @patch("context_use.proxy.handler.litellm")
    async def test_returns_completion(self, mock_litellm: MagicMock) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        app = create_app(
            _make_handler(memories=[_make_result()]),
            upstream_url="https://api.openai.com",
        )
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
            )

        assert resp.status_code == 200
        assert resp.json()["choices"][0]["message"]["content"] == "Hi there!"

    @patch("context_use.proxy.handler.litellm")
    async def test_forwards_api_key(self, mock_litellm: MagicMock) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        app = create_app(_make_handler(), upstream_url="https://api.openai.com")
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
        assert (
            mock_litellm.acompletion.call_args.kwargs.get("api_key")
            == "sk-test-key-123"
        )


class TestStreaming:
    @patch("context_use.proxy.handler.litellm")
    async def test_returns_sse(self, mock_litellm: MagicMock) -> None:
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
        app = create_app(_make_handler(), upstream_url="https://api.openai.com")
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


class TestErrorHandling:
    @patch("context_use.proxy.handler.litellm")
    async def test_llm_error_returns_status(self, mock_litellm: MagicMock) -> None:
        exc = Exception("Rate limit exceeded")
        exc.status_code = 429  # type: ignore[attr-defined]
        mock_litellm.acompletion = AsyncMock(side_effect=exc)
        app = create_app(_make_handler(), upstream_url="https://api.openai.com")
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

    @patch("context_use.proxy.handler.litellm")
    async def test_generic_error_returns_500(self, mock_litellm: MagicMock) -> None:
        mock_litellm.acompletion = AsyncMock(side_effect=RuntimeError("boom"))
        app = create_app(_make_handler(), upstream_url="https://api.openai.com")
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
            )

        assert resp.status_code == 500


class TestSessionIdHeader:
    @patch("context_use.proxy.handler.litellm")
    async def test_session_id_extracted_from_header(
        self, mock_litellm: MagicMock
    ) -> None:
        mock_litellm.acompletion = AsyncMock(return_value=_mock_model_response())
        processor = _mock_processor()
        handler = ProxyHandler(_mock_ctx(), processor)
        app = create_app(handler, upstream_url="https://api.openai.com")
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={"ctxuse-session-id": "sess-abc"},
            )

        processor.schedule.assert_called_once()
        assert processor.schedule.call_args.kwargs["session_id"] == "sess-abc"


class TestPassThrough:
    @patch("context_use.server.app._make_http_client")
    async def test_unknown_path_forwarded_to_upstream(
        self, mock_factory: MagicMock
    ) -> None:
        upstream_response = MagicMock()
        upstream_response.status_code = 200
        upstream_response.headers.raw = [(b"content-type", b"application/json")]
        upstream_response.content = json.dumps({"object": "list", "data": []}).encode()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.request = AsyncMock(return_value=upstream_response)
        mock_factory.return_value = mock_client

        app = create_app(_make_handler(), upstream_url="https://api.openai.com")
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/v1/models")

        assert resp.status_code == 200
        mock_client.request.assert_called_once()
        call = mock_client.request.call_args
        assert call.kwargs["url"] == "https://api.openai.com/v1/models"
        assert call.kwargs["method"] == "GET"

    @patch("context_use.server.app._make_http_client")
    async def test_upstream_error_returns_502(self, mock_factory: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.request = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_factory.return_value = mock_client

        app = create_app(_make_handler(), upstream_url="https://api.openai.com")
        transport = ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/v1/models")

        assert resp.status_code == 502

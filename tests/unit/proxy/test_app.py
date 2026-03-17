from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from httpx import ASGITransport

from context_use.proxy.app import (
    _ALLOWED_UPSTREAM_HOSTS,
    SESSION_ID_HEADER,
    create_proxy_app,
)
from context_use.proxy.background import BackgroundMemoryProcessor
from context_use.proxy.handler import ContextProxy
from context_use.store.base import MemorySearchResult


async def _aiter(*items: bytes) -> AsyncGenerator[bytes, None]:
    for item in items:
        yield item


def _transport(app: Any) -> ASGITransport:
    return ASGITransport(app=app)  # type: ignore[arg-type]


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
) -> ContextProxy:
    return ContextProxy(_mock_ctx(memories), _mock_processor())


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


class TestMissingHostHeader:
    async def test_returns_400_when_host_absent(self) -> None:
        responses: list[dict[str, Any]] = []

        async def mock_receive() -> dict[str, Any]:
            return {"body": b"", "more_body": False}

        async def mock_send(message: dict[str, Any]) -> None:
            responses.append(message)

        app = create_proxy_app(_make_handler())
        await app(
            {
                "type": "http",
                "method": "POST",
                "path": "/v1/chat/completions",
                "headers": [],
                "query_string": b"",
            },
            mock_receive,
            mock_send,
        )

        assert responses[0]["status"] == 400
        body = json.loads(responses[1]["body"])
        assert "Host" in body["error"]["message"]

    async def test_returns_400_when_host_is_unknown(self) -> None:
        app = create_proxy_app(_make_handler())
        transport = _transport(app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://localhost:8080"
        ) as client:
            resp = await client.post("/v1/chat/completions", json=_completion_body())
        assert resp.status_code == 400
        body = resp.json()
        assert "localhost" in body["error"]["message"]

    async def test_returns_400_when_host_is_arbitrary_domain(self) -> None:
        app = create_proxy_app(_make_handler())
        transport = _transport(app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://my-custom-llm.example.com"
        ) as client:
            resp = await client.post("/v1/chat/completions", json=_completion_body())
        assert resp.status_code == 400

    async def test_allowed_host_passes_validation(self) -> None:
        host = next(iter(_ALLOWED_UPSTREAM_HOSTS))
        app = create_proxy_app(_make_handler())

        responses: list[dict[str, Any]] = []

        async def mock_receive() -> dict[str, Any]:
            return {"body": b"", "more_body": False}

        async def mock_send(message: dict[str, Any]) -> None:
            responses.append(message)

        await app(
            {
                "type": "http",
                "method": "GET",
                "path": "/v1/models",
                "headers": [(b"host", host.encode())],
                "query_string": b"",
            },
            mock_receive,
            mock_send,
        )

        assert responses[0]["status"] != 400


class TestConfiguredTargetHost:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_allows_requests_without_host_header(
        self, MockClient: MagicMock
    ) -> None:
        upstream_response = MagicMock()
        upstream_response.status_code = 200
        upstream_response.headers.raw = [(b"content-type", b"application/json")]
        upstream_response.content = json.dumps({"object": "list", "data": []}).encode()

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=upstream_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        app = create_proxy_app(_make_handler(), target_host="api.openai.com")
        responses: list[dict[str, Any]] = []

        async def mock_receive() -> dict[str, Any]:
            return {"body": b"", "more_body": False}

        async def mock_send(message: dict[str, Any]) -> None:
            responses.append(message)

        await app(
            {
                "type": "http",
                "method": "GET",
                "path": "/v1/models",
                "headers": [],
                "query_string": b"",
            },
            mock_receive,
            mock_send,
        )

        assert responses[0]["status"] == 200
        assert (
            mock_client.request.call_args.kwargs["url"]
            == "https://api.openai.com/v1/models"
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_ignores_request_host_when_target_host_is_configured(
        self, MockClient: MagicMock
    ) -> None:
        upstream_response = MagicMock()
        upstream_response.status_code = 200
        upstream_response.headers.raw = [(b"content-type", b"application/json")]
        upstream_response.content = json.dumps({"object": "list", "data": []}).encode()

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=upstream_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        app = create_proxy_app(_make_handler(), target_host="api.openai.com")
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://localhost:8080"
        ) as client:
            resp = await client.get("/v1/models")

        assert resp.status_code == 200
        assert (
            mock_client.request.call_args.kwargs["url"]
            == "https://api.openai.com/v1/models"
        )


class TestRequestValidation:
    async def test_missing_model(self) -> None:
        app = create_proxy_app(_make_handler())
        transport = _transport(app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.openai.com"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )
        assert resp.status_code == 400
        assert "required" in resp.json()["error"]["message"]

    async def test_missing_messages(self) -> None:
        app = create_proxy_app(_make_handler())
        transport = _transport(app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.openai.com"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4o"},
            )
        assert resp.status_code == 400

    async def test_invalid_json(self) -> None:
        app = create_proxy_app(_make_handler())
        transport = _transport(app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.openai.com"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                content=b"not json",
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 400
        assert "Invalid JSON" in resp.json()["error"]["message"]


class TestNonStreaming:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_returns_completion(self, MockClient: MagicMock) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        app = create_proxy_app(_make_handler(memories=[_make_result()]))
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.openai.com"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
            )

        assert resp.status_code == 200
        assert resp.json()["choices"][0]["message"]["content"] == "Hi there!"

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_host_header_determines_upstream(self, MockClient: MagicMock) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.openai.com"
        ) as client:
            await client.post("/v1/chat/completions", json=_completion_body())

        assert (
            mock_client.post.call_args.args[0]
            == "https://api.openai.com/v1/chat/completions"
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_authorization_header_forwarded(self, MockClient: MagicMock) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.openai.com"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={"Authorization": "Bearer sk-provider-key"},
            )

        forwarded = dict(mock_client.post.call_args.kwargs["headers"])
        assert forwarded.get(b"authorization") == b"Bearer sk-provider-key"

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_host_header_not_forwarded_to_upstream(
        self, MockClient: MagicMock
    ) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.openai.com"
        ) as client:
            await client.post("/v1/chat/completions", json=_completion_body())

        forwarded_keys = [k for k, _ in mock_client.post.call_args.kwargs["headers"]]
        assert b"host" not in forwarded_keys


class TestStreaming:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_streams_raw_bytes_from_upstream(self, MockClient: MagicMock) -> None:
        sse_chunk = (
            b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\ndata: [DONE]\n\n'
        )
        _setup_streaming_client(
            MockClient,
            _mock_streaming_response(
                headers=[(b"content-type", b"text/event-stream")],
                chunks=[sse_chunk],
            ),
        )
        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.openai.com"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(stream=True),
            )

        assert resp.status_code == 200
        assert sse_chunk in resp.content


class TestErrorHandling:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_upstream_error_returns_500(self, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("upstream down"))
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.openai.com"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
            )

        assert resp.status_code == 500
        assert "upstream down" in resp.json()["error"]["message"]


class TestSessionIdHeader:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_session_id_extracted_from_header(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        processor = _mock_processor()
        handler = ContextProxy(_mock_ctx(), processor)
        app = create_proxy_app(handler)
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.openai.com"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={SESSION_ID_HEADER: "sess-abc"},
            )

        processor.schedule.assert_called_once()
        assert processor.schedule.call_args.kwargs["session_id"] == "sess-abc"

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_session_id_header_not_forwarded_to_upstream(
        self, MockClient: MagicMock
    ) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.openai.com"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={SESSION_ID_HEADER: "sess-abc"},
            )

        forwarded_keys = [k for k, _ in mock_client.post.call_args.kwargs["headers"]]
        assert SESSION_ID_HEADER.encode() not in forwarded_keys


class TestPassThrough:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_unknown_path_forwarded_to_upstream(
        self, MockClient: MagicMock
    ) -> None:
        upstream_response = MagicMock()
        upstream_response.status_code = 200
        upstream_response.headers.raw = [(b"content-type", b"application/json")]
        upstream_response.content = json.dumps({"object": "list", "data": []}).encode()

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=upstream_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.openai.com"
        ) as client:
            resp = await client.get("/v1/models")

        assert resp.status_code == 200
        mock_client.request.assert_called_once()
        call = mock_client.request.call_args
        assert call.kwargs["url"] == "https://api.openai.com/v1/models"
        assert call.kwargs["method"] == "GET"

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_upstream_error_returns_500(self, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=Exception("refused"))
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://api.openai.com"
        ) as client:
            resp = await client.get("/v1/models")

        assert resp.status_code == 500

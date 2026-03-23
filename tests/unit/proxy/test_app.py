from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from httpx import ASGITransport

from context_use.proxy.app import _ALLOWED_UPSTREAM_HOSTS, create_proxy_app
from context_use.proxy.handler import ContextProxy
from context_use.proxy.headers import DEFAULT_PREFIX, ProxyHeaders
from context_use.store.base import MemorySearchResult

HEADERS = ProxyHeaders.from_prefix(DEFAULT_PREFIX)
_UPSTREAM = {HEADERS.upstream_host: "api.openai.com"}


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


def _make_handler(
    memories: list[MemorySearchResult] | None = None,
) -> ContextProxy:
    return ContextProxy(_mock_ctx(memories))


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
        "model": "gpt-5.2",
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
    mock_cls.return_value = mock_client
    return mock_client


def _mock_streaming_response(
    status: int = 200,
    headers: list[tuple[bytes, bytes]] | None = None,
    chunks: list[bytes] | None = None,
) -> AsyncMock:
    resp = AsyncMock()
    resp.status_code = status
    resp.headers.raw = headers or [(b"content-type", b"text/event-stream")]
    _chunks = chunks or []
    resp.aiter_bytes = MagicMock(return_value=_aiter(*_chunks))
    return resp


def _setup_streaming_client(mock_cls: MagicMock, response: AsyncMock) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.build_request = MagicMock(return_value=MagicMock())
    mock_client.send = AsyncMock(return_value=response)
    mock_cls.return_value = mock_client
    return mock_client


def _setup_passthrough_client(
    mock_cls: MagicMock,
    content: bytes,
    *,
    status: int = 200,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> AsyncMock:
    resp = AsyncMock()
    resp.status_code = status
    resp.headers.raw = headers or [(b"content-type", b"application/json")]
    resp.aiter_raw = MagicMock(return_value=_aiter(content))
    mock_client = AsyncMock()
    mock_client.build_request = MagicMock(return_value=MagicMock())
    mock_client.send = AsyncMock(return_value=resp)
    mock_cls.return_value = mock_client
    return mock_client


class TestMissingUpstreamHostHeader:
    async def test_returns_400_when_header_absent(self) -> None:
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
        assert "upstream host" in body["error"]["message"].lower()

    async def test_returns_400_when_host_is_unknown(self) -> None:
        app = create_proxy_app(_make_handler())
        transport = _transport(app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={HEADERS.upstream_host: "localhost:8080"},
            )
        assert resp.status_code == 400
        body = resp.json()
        assert "localhost" in body["error"]["message"]

    async def test_returns_400_when_host_is_arbitrary_domain(self) -> None:
        app = create_proxy_app(_make_handler())
        transport = _transport(app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={HEADERS.upstream_host: "my-custom-llm.example.com"},
            )
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
                "headers": [(HEADERS.upstream_host.encode(), host.encode())],
                "query_string": b"",
            },
            mock_receive,
            mock_send,
        )

        assert responses[0]["status"] != 400

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_full_url_form_accepted(self, MockClient: MagicMock) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={HEADERS.upstream_host: "https://api.openai.com"},
            )

        assert (
            mock_client.post.call_args.args[0]
            == "https://api.openai.com/v1/chat/completions"
        )

    async def test_full_url_with_unknown_host_returns_400(self) -> None:
        app = create_proxy_app(_make_handler())
        transport = _transport(app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={HEADERS.upstream_host: "https://evil.example.com"},
            )
        assert resp.status_code == 400
        assert "evil.example.com" in resp.json()["error"]["message"]

    async def test_full_url_with_invalid_scheme_returns_400(self) -> None:
        app = create_proxy_app(_make_handler())
        transport = _transport(app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={HEADERS.upstream_host: "ftp://api.openai.com"},
            )
        assert resp.status_code == 400
        assert "Invalid upstream host" in resp.json()["error"]["message"]


class TestConfiguredUpstreamUrl:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_allows_requests_without_headers_when_upstream_url_is_configured(
        self, MockClient: MagicMock
    ) -> None:
        content = json.dumps({"object": "list", "data": []}).encode()
        mock_client = _setup_passthrough_client(MockClient, content)

        app = create_proxy_app(_make_handler(), upstream_url="https://api.openai.com")
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
            mock_client.build_request.call_args.args[1]
            == "https://api.openai.com/v1/models"
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_ignores_upstream_host_header_when_upstream_url_is_configured(
        self, MockClient: MagicMock
    ) -> None:
        content = json.dumps({"object": "list", "data": []}).encode()
        mock_client = _setup_passthrough_client(MockClient, content)

        app = create_proxy_app(_make_handler(), upstream_url="https://api.openai.com")
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.get(
                "/v1/models",
                headers={HEADERS.upstream_host: "some-other-host.com"},
            )

        assert resp.status_code == 200
        assert (
            mock_client.build_request.call_args.args[1]
            == "https://api.openai.com/v1/models"
        )

    async def test_returns_400_for_invalid_upstream_url_scheme(self) -> None:
        app = create_proxy_app(_make_handler(), upstream_url="api.openai.com")
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.get("/v1/models")

        assert resp.status_code == 400
        assert "Invalid upstream URL" in resp.json()["error"]["message"]


class TestRequestValidation:
    async def test_missing_model(self) -> None:
        app = create_proxy_app(_make_handler())
        transport = _transport(app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "Hi"}]},
                headers=_UPSTREAM,
            )
        assert resp.status_code == 400
        assert "required" in resp.json()["error"]["message"]

    async def test_missing_messages(self) -> None:
        app = create_proxy_app(_make_handler())
        transport = _transport(app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "gpt-5.2"},
                headers=_UPSTREAM,
            )
        assert resp.status_code == 400

    async def test_invalid_json(self) -> None:
        app = create_proxy_app(_make_handler())
        transport = _transport(app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                content=b"not json",
                headers={"content-type": "application/json", **_UPSTREAM},
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
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers=_UPSTREAM,
            )

        assert resp.status_code == 200
        assert resp.json()["choices"][0]["message"]["content"] == "Hi there!"

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_upstream_host_header_determines_upstream(
        self, MockClient: MagicMock
    ) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers=_UPSTREAM,
            )

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
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={"Authorization": "Bearer sk-provider-key", **_UPSTREAM},
            )

        forwarded = dict(mock_client.post.call_args.kwargs["headers"])
        assert forwarded.get(b"authorization") == b"Bearer sk-provider-key"

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_upstream_host_header_not_forwarded(
        self, MockClient: MagicMock
    ) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers=_UPSTREAM,
            )

        forwarded_keys = [k for k, _ in mock_client.post.call_args.kwargs["headers"]]
        assert HEADERS.upstream_host.encode() not in forwarded_keys


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
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(stream=True),
                headers=_UPSTREAM,
            )

        assert resp.status_code == 200
        assert sse_chunk in resp.content


class TestErrorHandling:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_upstream_error_returns_500(self, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("upstream down"))
        MockClient.return_value = mock_client
        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers=_UPSTREAM,
            )

        assert resp.status_code == 500
        assert "upstream down" in resp.json()["error"]["message"]


class TestSessionIdHeader:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_session_id_extracted_from_header(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        handler = ContextProxy(_mock_ctx())
        handler._store_and_schedule = AsyncMock()  # type: ignore[method-assign]
        app = create_proxy_app(handler)
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={HEADERS.session_id: "sess-abc", **_UPSTREAM},
            )

        handler._store_and_schedule.assert_called_once()
        assert handler._store_and_schedule.call_args.kwargs["session_id"] == "sess-abc"

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_configured_session_id_used_when_header_absent(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        handler = ContextProxy(_mock_ctx())
        handler._store_and_schedule = AsyncMock()  # type: ignore[method-assign]
        app = create_proxy_app(handler, session_id="sess-fixed")
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers=_UPSTREAM,
            )

        handler._store_and_schedule.assert_called_once()
        assert (
            handler._store_and_schedule.call_args.kwargs["session_id"] == "sess-fixed"
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_header_session_id_overrides_default_session_id(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        handler = ContextProxy(_mock_ctx())
        handler._store_and_schedule = AsyncMock()  # type: ignore[method-assign]
        app = create_proxy_app(handler, session_id="sess-fixed")
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={HEADERS.session_id: "sess-header", **_UPSTREAM},
            )

        handler._store_and_schedule.assert_called_once()
        assert (
            handler._store_and_schedule.call_args.kwargs["session_id"] == "sess-header"
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_session_id_header_not_forwarded_to_upstream(
        self, MockClient: MagicMock
    ) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={HEADERS.session_id: "sess-abc", **_UPSTREAM},
            )

        forwarded_keys = [k for k, _ in mock_client.post.call_args.kwargs["headers"]]
        assert HEADERS.session_id.encode() not in forwarded_keys


class TestPassThrough:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_unknown_path_forwarded_to_upstream(
        self, MockClient: MagicMock
    ) -> None:
        content = json.dumps({"object": "list", "data": []}).encode()
        mock_client = _setup_passthrough_client(MockClient, content)

        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.get("/v1/models", headers=_UPSTREAM)

        assert resp.status_code == 200
        mock_client.build_request.assert_called_once()
        assert (
            mock_client.build_request.call_args.args[1]
            == "https://api.openai.com/v1/models"
        )
        assert mock_client.build_request.call_args.args[0] == "GET"

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_upstream_error_returns_500(self, MockClient: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client.build_request = MagicMock(return_value=MagicMock())
        mock_client.send = AsyncMock(side_effect=Exception("refused"))
        MockClient.return_value = mock_client

        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.get("/v1/models", headers=_UPSTREAM)

        assert resp.status_code == 500


class TestEnrichEnabledHeader:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_enrich_enabled_header_not_forwarded(
        self, MockClient: MagicMock
    ) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        app = create_proxy_app(_make_handler())
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={HEADERS.enrich_enabled: "true", **_UPSTREAM},
            )

        forwarded_keys = [k for k, _ in mock_client.post.call_args.kwargs["headers"]]
        assert HEADERS.enrich_enabled.encode() not in forwarded_keys

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_enrich_enabled_false_skips_enrichment(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        ctx = _mock_ctx(memories=[_make_result()])
        handler = ContextProxy(ctx)
        app = create_proxy_app(handler)
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={HEADERS.enrich_enabled: "false", **_UPSTREAM},
            )

        ctx.search_memories.assert_not_awaited()

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_enrich_enabled_defaults_to_true(self, MockClient: MagicMock) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        ctx = _mock_ctx(memories=[_make_result()])
        handler = ContextProxy(ctx)
        app = create_proxy_app(handler)
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers=_UPSTREAM,
            )

        ctx.search_memories.assert_awaited_once()
        sent_body = json.loads(mock_client.post.call_args.kwargs["content"])
        assert any(
            "Likes pizza" in str(m.get("content", "")) for m in sent_body["messages"]
        )


class TestCustomHeaderPrefix:
    @patch("context_use.proxy.handler.AsyncClient")
    async def test_custom_prefix_session_id(self, MockClient: MagicMock) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        handler = ContextProxy(_mock_ctx())
        handler._store_and_schedule = AsyncMock()  # type: ignore[method-assign]
        custom = ProxyHeaders.from_prefix("myproxy")
        app = create_proxy_app(handler, header_prefix="myproxy")
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={
                    custom.session_id: "sess-custom",
                    custom.upstream_host: "api.openai.com",
                },
            )

        handler._store_and_schedule.assert_called_once()
        assert (
            handler._store_and_schedule.call_args.kwargs["session_id"] == "sess-custom"
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_default_session_id_header_ignored_with_custom_prefix(
        self, MockClient: MagicMock
    ) -> None:
        _setup_non_streaming_client(MockClient, _mock_http_response())
        handler = ContextProxy(_mock_ctx())
        handler._store_and_schedule = AsyncMock()  # type: ignore[method-assign]
        custom = ProxyHeaders.from_prefix("myproxy")
        app = create_proxy_app(
            handler, session_id="sess-default", header_prefix="myproxy"
        )
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={
                    HEADERS.session_id: "sess-ignored",
                    custom.upstream_host: "api.openai.com",
                },
            )

        handler._store_and_schedule.assert_called_once()
        assert (
            handler._store_and_schedule.call_args.kwargs["session_id"] == "sess-default"
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_custom_prefix_upstream_host(self, MockClient: MagicMock) -> None:
        mock_client = _setup_non_streaming_client(MockClient, _mock_http_response())
        custom = ProxyHeaders.from_prefix("myproxy")
        app = create_proxy_app(_make_handler(), header_prefix="myproxy")
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers={custom.upstream_host: "api.openai.com"},
            )

        assert (
            mock_client.post.call_args.args[0]
            == "https://api.openai.com/v1/chat/completions"
        )

    @patch("context_use.proxy.handler.AsyncClient")
    async def test_default_upstream_host_header_ignored_with_custom_prefix(
        self, MockClient: MagicMock
    ) -> None:
        app = create_proxy_app(_make_handler(), header_prefix="myproxy")
        transport = _transport(app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json=_completion_body(),
                headers=_UPSTREAM,
            )

        assert resp.status_code == 400
        body = resp.json()
        assert "upstream host" in body["error"]["message"].lower()

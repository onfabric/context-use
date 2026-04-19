from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from context_use.core import ContextUse
from context_use.store.base import ThreadSearchResult


def _make_ctx(*, search_results: list[ThreadSearchResult]) -> ContextUse:
    store = AsyncMock()
    store.search_threads = AsyncMock(return_value=search_results)

    llm_client = MagicMock()
    llm_client.embed_query = AsyncMock(return_value=[1.0, 0.0, 0.0])

    ctx = object.__new__(ContextUse)
    ctx._store = store
    ctx._llm_client = llm_client
    ctx._storage = MagicMock()
    return ctx


class TestSearchThreads:
    @pytest.mark.asyncio
    async def test_embeds_query_and_delegates_to_store(self) -> None:
        from datetime import UTC, datetime

        hit = ThreadSearchResult(
            id="t1",
            interaction_type="chatgpt_conversations",
            content="hello world",
            asat=datetime(2025, 1, 1, tzinfo=UTC),
            similarity=0.95,
        )
        ctx = _make_ctx(search_results=[hit])

        results = await ctx.search_threads("hello")

        assert len(results) == 1
        assert results[0].id == "t1"
        assert results[0].similarity == 0.95

        ctx._llm_client.embed_query.assert_awaited_once_with("hello")  # type: ignore[union-attr]
        ctx._store.search_threads.assert_awaited_once()  # type: ignore[union-attr]
        call_kwargs = ctx._store.search_threads.call_args.kwargs  # type: ignore[union-attr]
        assert call_kwargs["query_embedding"] == [1.0, 0.0, 0.0]
        assert call_kwargs["top_k"] == 10

    @pytest.mark.asyncio
    async def test_forwards_top_k_and_interaction_types(self) -> None:
        ctx = _make_ctx(search_results=[])

        await ctx.search_threads(
            "query",
            top_k=5,
            interaction_types=["instagram_posts"],
        )

        call_kwargs = ctx._store.search_threads.call_args.kwargs  # type: ignore[union-attr]
        assert call_kwargs["top_k"] == 5
        assert call_kwargs["interaction_types"] == ["instagram_posts"]

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_results(self) -> None:
        ctx = _make_ctx(search_results=[])
        results = await ctx.search_threads("nothing")
        assert results == []

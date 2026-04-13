from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from context_use.llm.base import EmbedItem
from context_use.models.thread import Thread
from context_use.thread_embedding.embedding import (
    store_thread_embeddings,
    submit_thread_embeddings,
)


def _make_thread(
    thread_id: str = "t1",
    content: str | None = "Hello world",
) -> Thread:
    return Thread(
        id=thread_id,
        unique_key=f"uk-{thread_id}",
        provider="test",
        interaction_type="test_type",
        payload={
            "type": "Create",
            "fibre_kind": "Create",
            "object": {"type": "Note", "content": content or ""},
        },
        version="1.0.0",
        asat=datetime(2025, 1, 1, tzinfo=UTC),
        content=content,
    )


class TestSubmitThreadEmbeddings:
    @pytest.mark.asyncio
    async def test_builds_embed_items_and_submits(self) -> None:
        t1 = _make_thread("t1", "First thread")
        t2 = _make_thread("t2", "Second thread")
        llm = AsyncMock()
        llm.embed_batch_submit = AsyncMock(return_value="job-123")

        key = await submit_thread_embeddings([t1, t2], "batch-1", llm)

        assert key == "job-123"
        llm.embed_batch_submit.assert_called_once()
        _, items = llm.embed_batch_submit.call_args.args
        assert len(items) == 2
        assert all(isinstance(i, EmbedItem) for i in items)
        assert items[0].item_id == "t1"
        assert items[0].text == "First thread"

    @pytest.mark.asyncio
    async def test_skips_empty_content(self) -> None:
        t1 = _make_thread("t1", "Has content")
        t2 = _make_thread("t2", "")
        t3 = _make_thread("t3", "   ")
        llm = AsyncMock()
        llm.embed_batch_submit = AsyncMock(return_value="job-456")

        await submit_thread_embeddings([t1, t2, t3], "batch-2", llm)

        _, items = llm.embed_batch_submit.call_args.args
        assert len(items) == 1
        assert items[0].item_id == "t1"

    @pytest.mark.asyncio
    async def test_raises_when_all_empty(self) -> None:
        t1 = _make_thread("t1", "")
        llm = AsyncMock()

        with pytest.raises(ValueError, match="No threads with non-empty content"):
            await submit_thread_embeddings([t1], "batch-3", llm)


class TestStoreThreadEmbeddings:
    @pytest.mark.asyncio
    async def test_upserts_each_result(self) -> None:
        store = AsyncMock()
        store.upsert_thread_embedding = AsyncMock()

        results = {"t1": [0.1, 0.2], "t2": [0.3, 0.4]}
        count = await store_thread_embeddings(results, "batch-1", store)

        assert count == 2
        assert store.upsert_thread_embedding.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_results(self) -> None:
        store = AsyncMock()
        count = await store_thread_embeddings({}, "batch-2", store)
        assert count == 0

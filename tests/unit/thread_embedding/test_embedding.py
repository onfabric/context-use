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
    *,
    thread_id: str = "t1",
    asset_uri: str | None = None,
    content: str | None = None,
    caption: str | None = "hello world",
) -> Thread:
    obj: dict = {"type": "Note", "fibre_kind": "TextMessage"}
    if caption is not None:
        obj["content"] = caption
    payload: dict = {
        "type": "Create",
        "fibre_kind": "SendMessage",
        "object": obj,
        "target": {"type": "Application", "name": "assistant"},
    }
    return Thread(
        id=thread_id,
        unique_key=f"uk-{thread_id}",
        provider="ChatGPT",
        interaction_type="chatgpt_conversations",
        payload=payload,
        version="1.1.0",
        asat=datetime(2025, 1, 1, tzinfo=UTC),
        asset_uri=asset_uri,
        content=content,
    )


class TestSubmitThreadEmbeddings:
    @pytest.mark.asyncio
    async def test_submits_embeddable_threads(self) -> None:
        threads = [_make_thread(thread_id="t1"), _make_thread(thread_id="t2")]
        llm = AsyncMock()
        llm.embed_batch_submit = AsyncMock(return_value="job-1")

        job_key, ids = await submit_thread_embeddings(threads, "batch-1", llm)

        assert job_key == "job-1"
        assert ids == ["t1", "t2"]
        items = llm.embed_batch_submit.call_args[0][1]
        assert len(items) == 2
        assert all(isinstance(i, EmbedItem) for i in items)

    @pytest.mark.asyncio
    async def test_skips_threads_without_embeddable_content(self) -> None:
        threads = [
            _make_thread(thread_id="t1", caption="hello"),
            _make_thread(thread_id="t2", caption=None, asset_uri="pic.jpg"),
        ]
        llm = AsyncMock()
        llm.embed_batch_submit = AsyncMock(return_value="job-1")

        job_key, ids = await submit_thread_embeddings(threads, "batch-1", llm)

        assert ids == ["t1"]

    @pytest.mark.asyncio
    async def test_raises_when_no_embeddable_content(self) -> None:
        threads = [
            _make_thread(thread_id="t1", caption=None, asset_uri="pic.jpg"),
        ]
        llm = AsyncMock()

        with pytest.raises(ValueError, match="No threads with embeddable content"):
            await submit_thread_embeddings(threads, "batch-1", llm)


class TestStoreThreadEmbeddings:
    @pytest.mark.asyncio
    async def test_stores_all_results(self) -> None:
        store = AsyncMock()
        results = {"t1": [1.0, 0.0], "t2": [0.0, 1.0]}

        count = await store_thread_embeddings(results, "batch-1", store)

        assert count == 2
        assert store.upsert_thread_embedding.await_count == 2

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_results(self) -> None:
        store = AsyncMock()
        count = await store_thread_embeddings({}, "batch-1", store)
        assert count == 0

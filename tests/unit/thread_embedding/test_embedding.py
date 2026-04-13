from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from context_use.models.thread import Thread
from context_use.thread_embedding.embedding import (
    store_thread_embeddings,
    submit_thread_embeddings,
)


def _comment_payload(text: str) -> dict:
    return {
        "type": "Create",
        "fibre_kind": "Comment",
        "object": {"type": "Note", "content": text},
    }


def _asset_payload() -> dict:
    return {
        "type": "Create",
        "fibre_kind": "Create",
        "object": {"type": "Image"},
    }


def _make_thread(
    thread_id: str = "t1",
    content: str | None = None,
    asset_uri: str | None = None,
    payload_content: str = "raw payload text",
) -> Thread:
    payload = _asset_payload() if asset_uri else _comment_payload(payload_content)
    return Thread(
        id=thread_id,
        unique_key=f"uk-{thread_id}",
        provider="test",
        interaction_type="test_type",
        payload=payload,
        version="1.0.0",
        asat=datetime(2025, 1, 1, tzinfo=UTC),
        content=content,
        asset_uri=asset_uri,
    )


class TestSubmitThreadEmbeddings:
    @pytest.mark.asyncio
    async def test_non_asset_uses_raw_content(self) -> None:
        t = _make_thread("t1", payload_content="raw text")
        llm = AsyncMock()
        llm.embed_batch_submit = AsyncMock(return_value="job-1")

        await submit_thread_embeddings([t], "batch-1", llm)

        _, items = llm.embed_batch_submit.call_args.args
        assert len(items) == 1
        assert items[0].text == "raw text"

    @pytest.mark.asyncio
    async def test_asset_with_description_uses_description(self) -> None:
        t = _make_thread(
            "t1",
            content="A sunset over the ocean",
            asset_uri="archive/pic.jpg",
            payload_content="caption",
        )
        llm = AsyncMock()
        llm.embed_batch_submit = AsyncMock(return_value="job-2")

        await submit_thread_embeddings([t], "batch-2", llm)

        _, items = llm.embed_batch_submit.call_args.args
        assert items[0].text == "A sunset over the ocean"

    @pytest.mark.asyncio
    async def test_asset_without_description_is_skipped(self) -> None:
        described = _make_thread("t1", content="described", asset_uri="archive/a.jpg")
        undescribed = _make_thread("t2", content=None, asset_uri="archive/b.jpg")
        llm = AsyncMock()
        llm.embed_batch_submit = AsyncMock(return_value="job-3")

        await submit_thread_embeddings([described, undescribed], "batch-3", llm)

        _, items = llm.embed_batch_submit.call_args.args
        assert len(items) == 1
        assert items[0].item_id == "t1"

    @pytest.mark.asyncio
    async def test_skips_empty_content(self) -> None:
        t1 = _make_thread("t1", payload_content="has content")
        t2 = _make_thread("t2", payload_content="")
        t3 = _make_thread("t3", payload_content="   ")
        llm = AsyncMock()
        llm.embed_batch_submit = AsyncMock(return_value="job-4")

        await submit_thread_embeddings([t1, t2, t3], "batch-4", llm)

        _, items = llm.embed_batch_submit.call_args.args
        assert len(items) == 1
        assert items[0].item_id == "t1"

    @pytest.mark.asyncio
    async def test_raises_when_none_embeddable(self) -> None:
        t = _make_thread("t1", payload_content="")
        llm = AsyncMock()

        with pytest.raises(ValueError, match="No threads with embeddable content"):
            await submit_thread_embeddings([t], "batch-5", llm)


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

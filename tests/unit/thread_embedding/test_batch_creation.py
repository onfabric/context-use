from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from context_use.core import ContextUse
from context_use.models.thread import Thread


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
    return Thread(
        id=thread_id,
        unique_key=f"uk-{thread_id}",
        provider="ChatGPT",
        interaction_type="chatgpt_conversations",
        payload={
            "type": "Create",
            "fibre_kind": "SendMessage",
            "object": obj,
            "target": {"type": "Application", "name": "assistant"},
        },
        version="1.1.0",
        asat=datetime(2025, 1, 1, tzinfo=UTC),
        asset_uri=asset_uri,
        content=content,
    )


def _make_ctx(*, threads: list[Thread]) -> ContextUse:
    store = AsyncMock()
    store.get_unprocessed_threads = AsyncMock(return_value=threads)
    store.create_batch = AsyncMock(side_effect=lambda b, _groups: b)

    ctx = object.__new__(ContextUse)
    ctx._store = store
    ctx._llm_client = MagicMock()
    ctx._storage = MagicMock()
    return ctx


class TestCreateThreadEmbeddingBatches:
    @pytest.mark.asyncio
    async def test_creates_batches_for_embeddable_threads(self) -> None:
        threads = [
            _make_thread(thread_id="t1", caption="hello"),
            _make_thread(thread_id="t2", caption="world"),
        ]
        ctx = _make_ctx(threads=threads)

        batches = await ctx.create_thread_embedding_batches()

        assert len(batches) == 1

    @pytest.mark.asyncio
    async def test_skips_undescribed_asset_threads(self) -> None:
        threads = [
            _make_thread(thread_id="text", caption="hello"),
            _make_thread(thread_id="asset", asset_uri="pic.jpg", caption=None),
        ]
        ctx = _make_ctx(threads=threads)

        with patch(
            "context_use.thread_embedding.factory.ThreadEmbeddingBatchFactory.create_batches",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_create:
            await ctx.create_thread_embedding_batches()
            groups = mock_create.call_args[0][0]

        group_ids = [g.group_id for g in groups]
        assert "text" in group_ids
        assert "asset" not in group_ids

    @pytest.mark.asyncio
    async def test_includes_described_asset_threads(self) -> None:
        threads = [
            _make_thread(
                thread_id="asset",
                asset_uri="pic.jpg",
                content="A sunset",
                caption=None,
            ),
        ]
        ctx = _make_ctx(threads=threads)

        batches = await ctx.create_thread_embedding_batches()

        assert len(batches) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_embeddable(self) -> None:
        threads = [
            _make_thread(thread_id="asset", asset_uri="pic.jpg", caption=None),
        ]
        ctx = _make_ctx(threads=threads)

        batches = await ctx.create_thread_embedding_batches()
        assert batches == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_threads(self) -> None:
        ctx = _make_ctx(threads=[])
        batches = await ctx.create_thread_embedding_batches()
        assert batches == []

    @pytest.mark.asyncio
    async def test_forwards_task_id_to_store(self) -> None:
        ctx = _make_ctx(threads=[])
        await ctx.create_thread_embedding_batches(task_id="task-42")

        mock: AsyncMock = ctx._store.get_unprocessed_threads  # type: ignore[assignment]
        mock.assert_awaited_once()
        assert mock.call_args.kwargs["task_id"] == "task-42"

    @pytest.mark.asyncio
    async def test_forwards_since_to_store(self) -> None:
        since = datetime(2025, 6, 1, tzinfo=UTC)
        ctx = _make_ctx(threads=[])
        await ctx.create_thread_embedding_batches(since=since)

        mock: AsyncMock = ctx._store.get_unprocessed_threads  # type: ignore[assignment]
        assert mock.call_args.kwargs["since"] == since

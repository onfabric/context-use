from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from context_use.batch.grouper import ThreadGroup
from context_use.batch.manager import BatchContext
from context_use.batch.states import CompleteState, CreatedState, SkippedState
from context_use.models.batch import Batch, BatchCategory
from context_use.models.thread import Thread
from context_use.thread_embedding.manager import ThreadEmbeddingBatchManager
from context_use.thread_embedding.states import (
    ThreadEmbedCompleteState,
    ThreadEmbedPendingState,
)


def _make_batch() -> Batch:
    return Batch(
        batch_number=1,
        category=BatchCategory.thread_embedding.value,
        states=[CreatedState().model_dump(mode="json")],
    )


def _make_thread(
    *,
    thread_id: str = "t1",
    caption: str = "hello world",
    asset_uri: str | None = None,
    content: str | None = None,
) -> Thread:
    obj: dict = {"type": "Note", "fibre_kind": "TextMessage", "content": caption}
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


def _make_ctx() -> BatchContext:
    return BatchContext(
        store=AsyncMock(),
        llm_client=AsyncMock(),
        storage=MagicMock(),
    )


class TestThreadEmbeddingBatchManager:
    @pytest.mark.asyncio
    async def test_full_state_machine(self) -> None:
        batch = _make_batch()
        thread = _make_thread()
        ctx = _make_ctx()
        ctx.llm_client.embed_batch_submit = AsyncMock(return_value="embed-job-1")
        ctx.llm_client.embed_batch_get_results = AsyncMock(
            return_value={thread.id: [1.0, 0.0, 0.0]}
        )

        manager = ThreadEmbeddingBatchManager(batch, ctx)

        with patch.object(
            manager.batch_factory,
            "get_batch_groups",
            return_value=[ThreadGroup(threads=[thread], group_id=thread.id)],
        ):
            state = await manager._transition(CreatedState())
        assert isinstance(state, ThreadEmbedPendingState)
        assert state.job_key == "embed-job-1"

        state2 = await manager._transition(state)
        assert isinstance(state2, ThreadEmbedCompleteState)
        assert state2.embedded_count == 1

        state3 = await manager._transition(state2)
        assert isinstance(state3, CompleteState)

    @pytest.mark.asyncio
    async def test_polls_while_results_none(self) -> None:
        batch = _make_batch()
        ctx = _make_ctx()
        ctx.llm_client.embed_batch_get_results = AsyncMock(return_value=None)

        manager = ThreadEmbeddingBatchManager(batch, ctx)
        pending = ThreadEmbedPendingState(job_key="job-1")

        state = await manager._transition(pending)
        assert isinstance(state, ThreadEmbedPendingState)
        assert state.job_key == "job-1"

    @pytest.mark.asyncio
    async def test_skip_when_no_embeddable_threads(self) -> None:
        batch = _make_batch()
        ctx = _make_ctx()
        # Asset thread with no description -> get_embeddable_content() returns None
        thread = _make_thread(asset_uri="pic.jpg")
        manager = ThreadEmbeddingBatchManager(batch, ctx)

        with patch.object(
            manager.batch_factory,
            "get_batch_groups",
            return_value=[ThreadGroup(threads=[thread], group_id=thread.id)],
        ):
            state = await manager._transition(CreatedState())
        assert isinstance(state, SkippedState)

    @pytest.mark.asyncio
    async def test_skip_when_no_groups(self) -> None:
        batch = _make_batch()
        ctx = _make_ctx()
        manager = ThreadEmbeddingBatchManager(batch, ctx)

        with patch.object(
            manager.batch_factory,
            "get_batch_groups",
            return_value=[],
        ):
            state = await manager._transition(CreatedState())
        assert isinstance(state, SkippedState)

    @pytest.mark.asyncio
    async def test_mixed_threads_skips_undescribed_assets(self) -> None:
        batch = _make_batch()
        ctx = _make_ctx()
        ctx.llm_client.embed_batch_submit = AsyncMock(return_value="embed-job-2")

        text_thread = _make_thread(thread_id="text-1", caption="some text")
        asset_thread = _make_thread(thread_id="asset-1", asset_uri="pic.jpg")
        described_asset = _make_thread(
            thread_id="asset-2",
            asset_uri="pic2.jpg",
            content="A beautiful sunset",
        )

        groups = [
            ThreadGroup(threads=[text_thread], group_id=text_thread.id),
            ThreadGroup(threads=[asset_thread], group_id=asset_thread.id),
            ThreadGroup(threads=[described_asset], group_id=described_asset.id),
        ]

        manager = ThreadEmbeddingBatchManager(batch, ctx)

        with patch.object(
            manager.batch_factory,
            "get_batch_groups",
            return_value=groups,
        ):
            state = await manager._transition(CreatedState())
        assert isinstance(state, ThreadEmbedPendingState)

        # Verify only 2 threads were submitted (text + described asset)
        items = ctx.llm_client.embed_batch_submit.call_args[0][1]
        submitted_ids = [item.item_id for item in items]
        assert "text-1" in submitted_ids
        assert "asset-2" in submitted_ids
        assert "asset-1" not in submitted_ids

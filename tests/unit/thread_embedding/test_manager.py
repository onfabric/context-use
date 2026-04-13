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
    thread_id: str = "t1",
    content: str | None = "Some content to embed",
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


def _make_ctx() -> BatchContext:
    return BatchContext(
        store=MagicMock(),
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
            return_value={thread.id: [0.1, 0.2, 0.3]}
        )
        ctx.store.upsert_thread_embedding = AsyncMock()

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
    async def test_skip_when_no_threads(self) -> None:
        batch = _make_batch()
        ctx = _make_ctx()
        manager = ThreadEmbeddingBatchManager(batch, ctx)

        with patch.object(manager.batch_factory, "get_batch_groups", return_value=[]):
            state = await manager._transition(CreatedState())
        assert isinstance(state, SkippedState)

    @pytest.mark.asyncio
    async def test_skip_when_all_empty_content(self) -> None:
        batch = _make_batch()
        thread = _make_thread(content="")
        ctx = _make_ctx()
        manager = ThreadEmbeddingBatchManager(batch, ctx)

        with patch.object(
            manager.batch_factory,
            "get_batch_groups",
            return_value=[ThreadGroup(threads=[thread], group_id=thread.id)],
        ):
            state = await manager._transition(CreatedState())
        assert isinstance(state, SkippedState)

    @pytest.mark.asyncio
    async def test_polling_returns_same_state(self) -> None:
        batch = _make_batch()
        ctx = _make_ctx()
        ctx.llm_client.embed_batch_get_results = AsyncMock(return_value=None)

        manager = ThreadEmbeddingBatchManager(batch, ctx)
        pending = ThreadEmbedPendingState(job_key="job-1")

        state = await manager._transition(pending)
        assert isinstance(state, ThreadEmbedPendingState)
        assert state.job_key == "job-1"

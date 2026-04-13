from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from context_use.asset_description.manager import AssetDescriptionBatchManager
from context_use.asset_description.prompt import AssetDescriptionSchema
from context_use.asset_description.states import (
    DescGenerateCompleteState,
    DescGeneratePendingState,
)
from context_use.batch.grouper import ThreadGroup
from context_use.batch.manager import BatchContext
from context_use.batch.states import CompleteState, CreatedState, SkippedState
from context_use.models.batch import Batch, BatchCategory
from context_use.models.thread import Thread


def _make_batch() -> Batch:
    return Batch(
        batch_number=1,
        category=BatchCategory.asset_description.value,
        states=[CreatedState().model_dump(mode="json")],
    )


def _make_thread(
    *,
    thread_id: str = "t1",
    asset_uri: str | None = "archive/pic.jpg",
    caption: str | None = "sunset",
) -> Thread:
    obj: dict = {"type": "Image"}
    if caption is not None:
        obj["content"] = caption
    return Thread(
        id=thread_id,
        unique_key=f"uk-{thread_id}",
        provider="Instagram",
        interaction_type="instagram_posts",
        payload={"type": "Create", "fibre_kind": "Create", "object": obj},
        version="1.1.0",
        asat=datetime(2025, 1, 1, tzinfo=UTC),
        asset_uri=asset_uri,
    )


def _make_store() -> MagicMock:
    store = MagicMock()
    store.list_threads_by_ids = AsyncMock(return_value=[])
    store.update_thread_content = AsyncMock()
    return store


def _make_ctx(store: MagicMock | None = None) -> BatchContext:
    if store is None:
        store = _make_store()
    return BatchContext(
        store=store,
        llm_client=AsyncMock(),
        storage=MagicMock(),
    )


class TestAssetDescriptionBatchManager:
    @pytest.mark.asyncio
    async def test_full_state_machine(self) -> None:
        batch = _make_batch()
        thread = _make_thread()
        store = _make_store()
        store.list_threads_by_ids = AsyncMock(return_value=[thread])
        ctx = _make_ctx(store)
        ctx.llm_client.batch_submit = AsyncMock(return_value="openai-batch-123")
        ctx.llm_client.batch_get_results = AsyncMock(
            return_value={
                thread.id: AssetDescriptionSchema(description="A sunset over the ocean")
            }
        )

        manager = AssetDescriptionBatchManager(batch, ctx)

        with patch.object(
            manager.batch_factory,
            "get_batch_groups",
            return_value=[ThreadGroup(threads=[thread], group_id=thread.id)],
        ):
            state = await manager._transition(CreatedState())
        assert isinstance(state, DescGeneratePendingState)
        assert state.job_key == "openai-batch-123"
        ctx.llm_client.batch_submit.assert_called_once()

        state2 = await manager._transition(state)
        assert isinstance(state2, DescGenerateCompleteState)
        assert state2.descriptions_count == 1
        store.update_thread_content.assert_called_once()

        state3 = await manager._transition(state2)
        assert isinstance(state3, CompleteState)

    @pytest.mark.asyncio
    async def test_polls_while_results_none(self) -> None:
        batch = _make_batch()
        ctx = _make_ctx()
        ctx.llm_client.batch_get_results = AsyncMock(return_value=None)

        manager = AssetDescriptionBatchManager(batch, ctx)
        pending = DescGeneratePendingState(job_key="job-1")

        state = await manager._transition(pending)
        assert isinstance(state, DescGeneratePendingState)
        assert state.job_key == "job-1"

    @pytest.mark.asyncio
    async def test_skip_when_no_asset_threads(self) -> None:
        batch = _make_batch()
        ctx = _make_ctx()
        manager = AssetDescriptionBatchManager(batch, ctx)

        with patch.object(
            manager.batch_factory,
            "get_batch_groups",
            return_value=[],
        ):
            state = await manager._transition(CreatedState())
        assert isinstance(state, SkippedState)

    @pytest.mark.asyncio
    async def test_composed_content_includes_caption(self) -> None:
        thread = _make_thread(caption="Beautiful sunset")
        store = _make_store()
        store.list_threads_by_ids = AsyncMock(return_value=[thread])
        ctx = _make_ctx(store)

        manager = AssetDescriptionBatchManager(_make_batch(), ctx)
        results = {
            thread.id: AssetDescriptionSchema(
                description="A golden sunset over the ocean"
            )
        }
        await manager._store_descriptions(results)

        store.update_thread_content.assert_called_once_with(
            thread.id,
            "A golden sunset over the ocean\n\nBeautiful sunset",
        )

    @pytest.mark.asyncio
    async def test_composed_content_omits_caption_when_empty(self) -> None:
        thread = _make_thread(caption=None)
        store = _make_store()
        store.list_threads_by_ids = AsyncMock(return_value=[thread])
        ctx = _make_ctx(store)

        manager = AssetDescriptionBatchManager(_make_batch(), ctx)
        results = {thread.id: AssetDescriptionSchema(description="A cat on a roof")}
        await manager._store_descriptions(results)

        store.update_thread_content.assert_called_once_with(
            thread.id, "A cat on a roof"
        )

    @pytest.mark.asyncio
    async def test_skips_empty_descriptions(self) -> None:
        thread = _make_thread()
        store = _make_store()
        store.list_threads_by_ids = AsyncMock(return_value=[thread])
        ctx = _make_ctx(store)

        manager = AssetDescriptionBatchManager(_make_batch(), ctx)
        results = {thread.id: AssetDescriptionSchema(description="")}
        count = await manager._store_descriptions(results)

        assert count == 0
        store.update_thread_content.assert_not_called()

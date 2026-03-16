"""Tests for the facet-related transitions in MemoryBatchManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from context_use.batch.manager import BatchContext
from context_use.batch.states import CompleteState
from context_use.memories.manager import MemoryBatchManager
from context_use.memories.prompt.base import Memory, MemoryFacetExtract, MemorySchema
from context_use.memories.states import (
    FacetEmbedCompleteState,
    FacetEmbedPendingState,
)
from context_use.models.batch import Batch, BatchCategory
from context_use.models.facet import MemoryFacet


def _make_batch() -> Batch:
    return Batch(batch_number=1, category=BatchCategory.memories, states=[])


def _make_ctx(store: MagicMock, llm: MagicMock) -> BatchContext:
    storage = MagicMock()
    storage.resolve_uri = MagicMock(side_effect=lambda x: x)
    return BatchContext(store=store, llm_client=llm, storage=storage)


def _make_store() -> MagicMock:
    store = MagicMock()
    store.create_memory = AsyncMock(side_effect=lambda m: m)
    store.create_memory_facet = AsyncMock(side_effect=lambda f: f)
    store.get_unembedded_memory_facets = AsyncMock(return_value=[])
    store.get_unlinked_memory_facets = AsyncMock(return_value=[])
    store.get_batch = AsyncMock()
    store.update_batch = AsyncMock()
    store.atomic = MagicMock(return_value=_async_ctx_manager())
    return store


def _make_llm() -> MagicMock:
    llm = MagicMock()
    llm.embed_batch_submit = AsyncMock(return_value="job-123")
    llm.embed_batch_get_results = AsyncMock(return_value=None)
    return llm


class _AsyncCtxManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _async_ctx_manager() -> _AsyncCtxManager:
    return _AsyncCtxManager()


async def test_store_memories_creates_facets() -> None:
    store = _make_store()
    llm = _make_llm()
    batch = _make_batch()
    mgr: MemoryBatchManager = MemoryBatchManager(batch, _make_ctx(store, llm))

    schema = MemorySchema(
        memories=[
            Memory(
                content="Had coffee with Alice in Paris",
                from_date="2024-01-01",
                to_date="2024-01-01",
                facets=[
                    MemoryFacetExtract(facet_type="person", facet_value="Alice"),
                    MemoryFacetExtract(facet_type="location", facet_value="Paris"),
                ],
            )
        ]
    )

    memory_ids = await mgr._store_memories({"group-1": schema})

    assert len(memory_ids) == 1
    assert store.create_memory.await_count == 1
    assert store.create_memory_facet.await_count == 2

    calls = store.create_memory_facet.call_args_list
    facets_written = [c.args[0] for c in calls]
    types = {f.facet_type for f in facets_written}
    assert types == {"person", "location"}
    for f in facets_written:
        assert f.batch_id == batch.id
        assert f.memory_id == memory_ids[0]


async def test_store_memories_no_facets() -> None:
    store = _make_store()
    llm = _make_llm()
    batch = _make_batch()
    mgr: MemoryBatchManager = MemoryBatchManager(batch, _make_ctx(store, llm))

    schema = MemorySchema(
        memories=[
            Memory(
                content="Just a plain memory",
                from_date="2024-01-01",
                to_date="2024-01-01",
                facets=[],
            )
        ]
    )

    memory_ids = await mgr._store_memories({"group-1": schema})
    assert len(memory_ids) == 1
    store.create_memory_facet.assert_not_awaited()


async def test_trigger_facet_embedding_with_facets() -> None:
    store = _make_store()
    llm = _make_llm()
    batch = _make_batch()
    mgr: MemoryBatchManager = MemoryBatchManager(batch, _make_ctx(store, llm))

    facets = [
        MemoryFacet(memory_id="m1", facet_type="person", facet_value="Alice"),
        MemoryFacet(memory_id="m1", facet_type="location", facet_value="Paris"),
    ]
    store.get_unembedded_memory_facets = AsyncMock(return_value=facets)

    result = await mgr._trigger_facet_embedding()

    assert isinstance(result, FacetEmbedPendingState)
    assert result.job_key == "job-123"
    assert set(result.facet_ids) == {facets[0].id, facets[1].id}
    store.get_unembedded_memory_facets.assert_awaited_once_with(batch_id=batch.id)


async def test_trigger_facet_embedding_no_facets() -> None:
    store = _make_store()
    llm = _make_llm()
    batch = _make_batch()
    mgr: MemoryBatchManager = MemoryBatchManager(batch, _make_ctx(store, llm))

    store.get_unembedded_memory_facets = AsyncMock(return_value=[])

    result = await mgr._trigger_facet_embedding()

    assert isinstance(result, FacetEmbedCompleteState)
    assert result.embedded_count == 0
    llm.embed_batch_submit.assert_not_awaited()


async def test_check_facet_embedding_status_pending() -> None:
    store = _make_store()
    llm = _make_llm()
    batch = _make_batch()
    mgr: MemoryBatchManager = MemoryBatchManager(batch, _make_ctx(store, llm))

    llm.embed_batch_get_results = AsyncMock(return_value=None)
    state = FacetEmbedPendingState(job_key="job-abc", facet_ids=["f1", "f2"])

    result = await mgr._check_facet_embedding_status(state)

    assert result is state


async def test_check_facet_embedding_status_complete() -> None:
    store = _make_store()
    llm = _make_llm()
    batch = _make_batch()
    mgr: MemoryBatchManager = MemoryBatchManager(batch, _make_ctx(store, llm))

    embed_results = {"f1": [1.0, 0.0], "f2": [0.0, 1.0]}
    llm.embed_batch_get_results = AsyncMock(return_value=embed_results)
    store.create_facet_embedding = AsyncMock()

    state = FacetEmbedPendingState(job_key="job-abc", facet_ids=["f1", "f2"])
    result = await mgr._check_facet_embedding_status(state)

    assert isinstance(result, FacetEmbedCompleteState)
    assert result.embedded_count == 2


async def test_link_facets_calls_linker() -> None:
    store = _make_store()
    llm = _make_llm()
    batch = _make_batch()
    mgr: MemoryBatchManager = MemoryBatchManager(batch, _make_ctx(store, llm))

    unlinked = [
        MemoryFacet(memory_id="m1", facet_type="person", facet_value="Alice"),
    ]
    unlinked[0].embedding = [1.0, 0.0, 0.0]
    store.get_unlinked_memory_facets = AsyncMock(return_value=unlinked)
    mgr.linker.link = AsyncMock()

    await mgr._link_facets()

    store.get_unlinked_memory_facets.assert_awaited_once()
    mgr.linker.link.assert_awaited_once_with(unlinked)


async def test_link_facets_noop_when_empty() -> None:
    store = _make_store()
    llm = _make_llm()
    batch = _make_batch()
    mgr: MemoryBatchManager = MemoryBatchManager(batch, _make_ctx(store, llm))

    store.get_unlinked_memory_facets = AsyncMock(return_value=[])
    mgr.linker.link = AsyncMock()

    await mgr._link_facets()

    mgr.linker.link.assert_not_awaited()


async def test_transition_facet_embed_complete_returns_complete() -> None:
    store = _make_store()
    llm = _make_llm()
    batch = _make_batch()
    mgr: MemoryBatchManager = MemoryBatchManager(batch, _make_ctx(store, llm))

    store.get_unlinked_memory_facets = AsyncMock(return_value=[])

    result = await mgr._transition(FacetEmbedCompleteState(embedded_count=5))

    assert isinstance(result, CompleteState)

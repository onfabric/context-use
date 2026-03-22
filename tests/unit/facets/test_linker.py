"""Tests for SemanticFacetLinker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from context_use.facets.linker import SemanticFacetLinker
from context_use.models.facet import Facet, MemoryFacet


def _make_facet(
    facet_type: str = "person",
    facet_value: str = "Alice",
    embedding: list[float] | None = None,
) -> MemoryFacet:
    f = MemoryFacet(
        memory_id="mem-1",
        facet_type=facet_type,
        facet_value=facet_value,
    )
    f.embedding = embedding or [1.0, 0.0, 0.0]
    return f


def _make_store(
    *,
    find_result: Facet | None = None,
) -> MagicMock:
    store = MagicMock()
    store.find_similar_facet = AsyncMock(return_value=find_result)
    store.create_facet = AsyncMock(side_effect=lambda f: f)
    store.create_facet_embedding = AsyncMock()
    store.update_memory_facet = AsyncMock()
    store.atomic = MagicMock(return_value=_async_ctx_manager())
    return store


class _AsyncCtxManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _async_ctx_manager() -> _AsyncCtxManager:
    return _AsyncCtxManager()


async def test_link_hit_uses_existing_canonical() -> None:
    existing = Facet(facet_type="person", facet_canonical="Alice")
    store = _make_store(find_result=existing)
    linker = SemanticFacetLinker(store, threshold=0.75)

    facet = _make_facet()
    await linker.link([facet])

    store.find_similar_facet.assert_awaited_once_with(
        facet_type="person",
        embedding=facet.embedding,
        threshold=0.75,
    )
    store.create_facet.assert_not_awaited()
    store.create_facet_embedding.assert_not_awaited()
    store.update_memory_facet.assert_awaited_once()
    assert facet.facet_id == existing.id


async def test_link_miss_creates_canonical_and_embedding() -> None:
    store = _make_store(find_result=None)
    linker = SemanticFacetLinker(store, threshold=0.75)

    facet = _make_facet(facet_value="Bob")
    await linker.link([facet])

    store.create_facet.assert_awaited_once()
    created_facet: Facet = store.create_facet.call_args[0][0]
    assert created_facet.facet_type == "person"
    assert created_facet.facet_canonical == "Bob"

    store.create_facet_embedding.assert_awaited_once_with(
        created_facet.id, facet.embedding
    )
    store.update_memory_facet.assert_awaited_once()
    assert facet.facet_id == created_facet.id


async def test_link_multiple_facets() -> None:
    existing = Facet(facet_type="person", facet_canonical="Alice")
    store = _make_store(find_result=None)
    store.find_similar_facet = AsyncMock(side_effect=[existing, None])
    linker = SemanticFacetLinker(store, threshold=0.75)

    f1 = _make_facet(facet_value="Alice")
    f2 = _make_facet(facet_type="location", facet_value="Paris")
    await linker.link([f1, f2])

    assert f1.facet_id == existing.id
    assert f2.facet_id is not None
    assert store.create_facet.await_count == 1
    assert store.update_memory_facet.await_count == 2


async def test_link_skips_facet_with_no_embedding() -> None:
    store = _make_store()
    linker = SemanticFacetLinker(store)

    facet = MemoryFacet(memory_id="mem-1", facet_type="person", facet_value="Alice")
    assert facet.embedding is None

    await linker.link([facet])

    store.find_similar_facet.assert_not_awaited()
    store.update_memory_facet.assert_not_awaited()


async def test_link_empty_list_is_noop() -> None:
    store = _make_store()
    linker = SemanticFacetLinker(store)

    await linker.link([])

    store.find_similar_facet.assert_not_awaited()
    store.update_memory_facet.assert_not_awaited()

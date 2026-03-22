"""Tests for memory_facets, facets, and vec_facets store methods."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date

import pytest

from context_use.models import Batch, TapestryMemory
from context_use.models.facet import Facet, MemoryFacet
from context_use.store.sqlite import SqliteStore

_TEST_EMBEDDING_DIMS = 4


@pytest.fixture()
async def store(tmp_path) -> AsyncGenerator[SqliteStore]:
    s = SqliteStore(path=str(tmp_path / "test.db"))
    await s.init(embedding_dimensions=_TEST_EMBEDDING_DIMS)
    yield s
    await s.close()


def _make_embedding(seed: float = 1.0) -> list[float]:
    return [seed] + [0.0] * (_TEST_EMBEDDING_DIMS - 1)


async def _make_memory(store: SqliteStore, group_id: str = "g1") -> TapestryMemory:
    mem = TapestryMemory(
        content="test",
        from_date=date(2024, 1, 1),
        to_date=date(2024, 1, 5),
        group_id=group_id,
    )
    return await store.create_memory(mem)


async def _make_batch(store: SqliteStore) -> Batch:
    batch = Batch(batch_number=1, category="memories", states=[])
    return await store.create_batch(batch, [])


async def test_create_and_read_memory_facet(store: SqliteStore) -> None:
    mem = await _make_memory(store)
    facet = MemoryFacet(memory_id=mem.id, facet_type="person", facet_value="Alice")
    created = await store.create_memory_facet(facet)
    assert created.id == facet.id

    unembedded = await store.get_unembedded_memory_facets()
    assert len(unembedded) == 1
    assert unembedded[0].facet_value == "Alice"
    assert unembedded[0].embedding is None


async def test_get_unembedded_memory_facets_excludes_embedded(
    store: SqliteStore,
) -> None:
    mem = await _make_memory(store)
    f1 = MemoryFacet(memory_id=mem.id, facet_type="person", facet_value="Alice")
    f2 = MemoryFacet(memory_id=mem.id, facet_type="location", facet_value="London")
    await store.create_memory_facet(f1)
    await store.create_memory_facet(f2)

    await store.create_facet_embedding(f1.id, _make_embedding(1.0))

    unembedded = await store.get_unembedded_memory_facets()
    assert len(unembedded) == 1
    assert unembedded[0].id == f2.id


async def test_get_unembedded_memory_facets_batch_filter(store: SqliteStore) -> None:
    batch_a = await _make_batch(store)
    batch_b = await _make_batch(store)
    mem = await _make_memory(store)

    f_a = MemoryFacet(
        memory_id=mem.id, batch_id=batch_a.id, facet_type="person", facet_value="Alice"
    )
    f_b = MemoryFacet(
        memory_id=mem.id, batch_id=batch_b.id, facet_type="person", facet_value="Bob"
    )
    await store.create_memory_facet(f_a)
    await store.create_memory_facet(f_b)

    results_a = await store.get_unembedded_memory_facets(batch_id=batch_a.id)
    assert len(results_a) == 1
    assert results_a[0].facet_value == "Alice"

    results_b = await store.get_unembedded_memory_facets(batch_id=batch_b.id)
    assert len(results_b) == 1
    assert results_b[0].facet_value == "Bob"

    all_results = await store.get_unembedded_memory_facets()
    assert len(all_results) == 2


async def test_update_memory_facet_sets_facet_id(store: SqliteStore) -> None:
    mem = await _make_memory(store)
    facet_row = MemoryFacet(memory_id=mem.id, facet_type="person", facet_value="Alice")
    await store.create_memory_facet(facet_row)

    canonical = Facet(facet_type="person", facet_canonical="Alice")
    await store.create_facet(canonical)

    facet_row.facet_id = canonical.id
    await store.update_memory_facet(facet_row)

    unlinked = await store.get_unlinked_memory_facets()
    assert unlinked == []


async def test_get_unlinked_memory_facets(store: SqliteStore) -> None:
    mem = await _make_memory(store)
    f1 = MemoryFacet(memory_id=mem.id, facet_type="person", facet_value="Alice")
    f2 = MemoryFacet(memory_id=mem.id, facet_type="location", facet_value="Paris")
    await store.create_memory_facet(f1)
    await store.create_memory_facet(f2)

    await store.create_facet_embedding(f1.id, _make_embedding(1.0))
    await store.create_facet_embedding(f2.id, _make_embedding(0.5))

    unlinked = await store.get_unlinked_memory_facets()
    assert len(unlinked) == 2
    ids = {f.id for f in unlinked}
    assert f1.id in ids
    assert f2.id in ids
    for f in unlinked:
        assert f.embedding is not None

    canonical = Facet(facet_type="person", facet_canonical="Alice")
    await store.create_facet(canonical)
    f1.facet_id = canonical.id
    await store.update_memory_facet(f1)

    unlinked = await store.get_unlinked_memory_facets()
    assert len(unlinked) == 1
    assert unlinked[0].id == f2.id


async def test_create_facet(store: SqliteStore) -> None:
    facet = Facet(facet_type="person", facet_canonical="Alice")
    created = await store.create_facet(facet)
    assert created.id == facet.id
    assert created.facet_canonical == "Alice"


async def test_create_facet_embedding(store: SqliteStore) -> None:
    mem = await _make_memory(store)
    mf = MemoryFacet(memory_id=mem.id, facet_type="person", facet_value="Alice")
    await store.create_memory_facet(mf)

    embedding = _make_embedding(1.0)
    await store.create_facet_embedding(mf.id, embedding)

    unembedded = await store.get_unembedded_memory_facets()
    assert unembedded == []


async def test_find_similar_facet_hit(store: SqliteStore) -> None:
    canonical = Facet(facet_type="person", facet_canonical="Alice")
    await store.create_facet(canonical)
    emb = _make_embedding(1.0)
    await store.create_facet_embedding(canonical.id, emb)

    query = _make_embedding(1.0)
    result = await store.find_similar_facet("person", query, threshold=0.75)
    assert result is not None
    assert result.id == canonical.id


async def test_find_similar_facet_miss_below_threshold(store: SqliteStore) -> None:
    canonical = Facet(facet_type="person", facet_canonical="Alice")
    await store.create_facet(canonical)
    emb = [1.0] + [0.0] * (_TEST_EMBEDDING_DIMS - 1)
    await store.create_facet_embedding(canonical.id, emb)

    orthogonal = [0.0, 1.0] + [0.0] * (_TEST_EMBEDDING_DIMS - 2)
    result = await store.find_similar_facet("person", orthogonal, threshold=0.75)
    assert result is None


async def test_find_similar_facet_cross_type_isolation(store: SqliteStore) -> None:
    person_facet = Facet(facet_type="person", facet_canonical="Alice")
    await store.create_facet(person_facet)
    emb = _make_embedding(1.0)
    await store.create_facet_embedding(person_facet.id, emb)

    query = _make_embedding(1.0)
    result = await store.find_similar_facet("location", query, threshold=0.75)
    assert result is None

    result = await store.find_similar_facet("person", query, threshold=0.75)
    assert result is not None

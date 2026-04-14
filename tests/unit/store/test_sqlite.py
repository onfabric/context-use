from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta

import pytest

from context_use.batch.grouper import ThreadGroup
from context_use.etl.core.types import ThreadRow
from context_use.memories.context import GroupContextBuilder
from context_use.models import (
    Archive,
    ArchiveStatus,
    Batch,
    EtlTask,
    EtlTaskStatus,
    MemoryStatus,
    TapestryMemory,
)
from context_use.store.base import SortOrder
from context_use.store.sqlite import SqliteStore

_TEST_EMBEDDING_DIMS = 4


@pytest.fixture()
async def store(tmp_path) -> AsyncGenerator[SqliteStore]:
    s = SqliteStore(path=str(tmp_path / "test.db"))
    await s.init(embedding_dimensions=_TEST_EMBEDDING_DIMS)
    yield s
    await s.close()


@pytest.fixture()
async def task_id(store: SqliteStore) -> str:
    """Create a valid archive + task and return the task ID."""
    archive = Archive(provider="test")
    await store.create_archive(archive)
    task = EtlTask(
        archive_id=archive.id,
        provider="test",
        interaction_type="test_type",
        source_uris=["test.json"],
    )
    await store.create_task(task)
    return task.id


async def test_reset_clears_all_data(store: SqliteStore) -> None:
    archive = Archive(provider="test")
    await store.create_archive(archive)
    assert await store.get_archive(archive.id) is not None

    await store.reset()

    assert await store.get_archive(archive.id) is None


async def test_archive_crud(store: SqliteStore) -> None:
    archive = Archive(provider="instagram")
    created = await store.create_archive(archive)
    assert created.id == archive.id

    fetched = await store.get_archive(archive.id)
    assert fetched is not None
    assert fetched.provider == "instagram"

    archive.status = ArchiveStatus.COMPLETED.value
    await store.update_archive(archive)
    updated = await store.get_archive(archive.id)
    assert updated is not None
    assert updated.status == ArchiveStatus.COMPLETED.value


async def test_get_archive_returns_none_for_missing(store: SqliteStore) -> None:
    assert await store.get_archive("nonexistent") is None


async def test_task_crud(store: SqliteStore) -> None:
    archive = Archive(provider="chatgpt")
    await store.create_archive(archive)

    task = EtlTask(
        archive_id=archive.id,
        provider="chatgpt",
        interaction_type="chatgpt_conversations",
        source_uris=["archive/conversations.json"],
    )
    created = await store.create_task(task)
    assert created.id == task.id

    fetched = await store.get_task(task.id)
    assert fetched is not None
    assert fetched.source_uris == ["archive/conversations.json"]
    assert fetched.source_uri == "archive/conversations.json"

    task.status = EtlTaskStatus.COMPLETED.value
    task.error_count = 3
    await store.update_task(task)
    updated = await store.get_task(task.id)
    assert updated is not None
    assert updated.status == EtlTaskStatus.COMPLETED.value
    assert updated.error_count == 3


def _make_row(unique_key: str, **kwargs) -> ThreadRow:
    defaults = {
        "provider": "test",
        "interaction_type": "test_type",
        "preview": "preview",
        "payload": {"fibre_kind": "TextMessage", "content": "hello"},
        "version": "1",
        "asat": datetime(2024, 1, 15, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return ThreadRow(unique_key=unique_key, **defaults)


async def test_insert_threads_deduplicates(store: SqliteStore, task_id: str) -> None:
    rows = [_make_row("k1"), _make_row("k2"), _make_row("k1")]
    ids = await store.insert_threads(rows, task_id=task_id)
    assert len(ids) == 2
    assert len(set(ids)) == 2

    rows2 = [_make_row("k1"), _make_row("k3")]
    ids2 = await store.insert_threads(rows2, task_id=task_id)
    assert len(ids2) == 1
    assert ids2[0] not in ids


async def test_get_unprocessed_threads_ordered_by_asat(
    store: SqliteStore, task_id: str
) -> None:
    r1 = _make_row("k1", asat=datetime(2024, 3, 1, tzinfo=UTC))
    r2 = _make_row("k2", asat=datetime(2024, 1, 1, tzinfo=UTC))
    r3 = _make_row("k3", asat=datetime(2024, 2, 1, tzinfo=UTC))
    await store.insert_threads([r1, r2, r3], task_id=task_id)

    threads = await store.get_unprocessed_threads()
    assert len(threads) == 3
    assert [t.unique_key for t in threads] == ["k2", "k3", "k1"]


async def test_get_unprocessed_threads_excludes_batched(
    store: SqliteStore, task_id: str
) -> None:
    await store.insert_threads(
        [_make_row("k1"), _make_row("k2"), _make_row("k3")], task_id=task_id
    )
    all_threads = await store.get_unprocessed_threads()

    group = ThreadGroup(threads=all_threads[:1], group_id="g1")
    batch = Batch(batch_number=1, category="memories", states=[])
    await store.create_batch(batch, [group])

    remaining = await store.get_unprocessed_threads()
    assert len(remaining) == 2
    assert all_threads[0].id not in {t.id for t in remaining}


async def test_get_unprocessed_threads_scoped_by_category(
    store: SqliteStore, task_id: str
) -> None:
    await store.insert_threads(
        [_make_row("k1"), _make_row("k2"), _make_row("k3")], task_id=task_id
    )
    all_threads = await store.get_unprocessed_threads()

    group = ThreadGroup(threads=all_threads[:1], group_id="g1")
    batch = Batch(batch_number=1, category="other_category", states=[])
    await store.create_batch(batch, [group])

    remaining_any = await store.get_unprocessed_threads()
    assert len(remaining_any) == 2

    remaining_memories = await store.get_unprocessed_threads(batch_category="memories")
    assert len(remaining_memories) == 3

    remaining_other = await store.get_unprocessed_threads(
        batch_category="other_category"
    )
    assert len(remaining_other) == 2
    assert all_threads[0].id not in {t.id for t in remaining_other}


async def test_get_unprocessed_threads_interaction_type_filter(
    store: SqliteStore,
    task_id: str,
) -> None:
    await store.insert_threads(
        [
            _make_row("k1", interaction_type="type_a"),
            _make_row("k2", interaction_type="type_b"),
            _make_row("k3", interaction_type="type_a"),
        ],
        task_id=task_id,
    )

    threads = await store.get_unprocessed_threads(interaction_types=["type_a"])
    assert len(threads) == 2
    assert all(t.interaction_type == "type_a" for t in threads)


async def test_list_threads_asat_desc_limit(store: SqliteStore, task_id: str) -> None:
    coll = "https://example.com/c/1"
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    rows = [
        _make_row(
            f"k{i}",
            collection_id=coll,
            asat=base + timedelta(hours=i),
        )
        for i in range(5)
    ]
    await store.insert_threads(rows, task_id=task_id)
    got = await store.list_threads(
        collection_id=coll,
        limit=3,
        asat_order=SortOrder.DESC,
    )
    assert [t.unique_key for t in got] == ["k4", "k3", "k2"]


async def test_group_context_builder_loads_recent_collection_threads(
    store: SqliteStore,
    task_id: str,
) -> None:
    coll = "https://example.com/c/3"
    base = datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC)
    rows = [
        _make_row(
            f"k{i}",
            collection_id=coll,
            asat=base + timedelta(hours=i),
        )
        for i in range(12)
    ]
    await store.insert_threads(rows, task_id=task_id)
    all_t = await store.list_threads(collection_id=coll)
    ordered = sorted(all_t, key=lambda t: t.asat)
    group = ThreadGroup(threads=ordered[-4:], group_id="g1")

    ctx = await GroupContextBuilder(store).build(group)
    assert len(ctx.new_threads) == 4
    assert len(ctx.relevant_threads) == 8
    assert ctx.relevant_threads[0].asat <= ctx.relevant_threads[-1].asat


async def test_batch_crud_with_groups(store: SqliteStore, task_id: str) -> None:
    await store.insert_threads(
        [_make_row("k1"), _make_row("k2"), _make_row("k3")],
        task_id=task_id,
    )
    threads = await store.get_unprocessed_threads()

    group = ThreadGroup(threads=threads[:2], group_id="g1")
    batch = Batch(batch_number=1, category="memories", states=[{"status": "CREATED"}])
    created = await store.create_batch(batch, [group])
    assert created.id == batch.id

    fetched = await store.get_batch(batch.id)
    assert fetched is not None

    batch.states = [{"status": "COMPLETE"}]
    await store.update_batch(batch)
    updated = await store.get_batch(batch.id)
    assert updated is not None
    assert updated.states[0]["status"] == "COMPLETE"


async def test_get_batch_groups(store: SqliteStore, task_id: str) -> None:
    await store.insert_threads(
        [_make_row("k1"), _make_row("k2"), _make_row("k3")],
        task_id=task_id,
    )
    threads = await store.get_unprocessed_threads()

    g1 = ThreadGroup(threads=threads[:2], group_id="g1")
    g2 = ThreadGroup(threads=threads[2:], group_id="g2")

    batch = Batch(batch_number=1, category="memories", states=[])
    await store.create_batch(batch, [g1, g2])

    groups = await store.get_batch_groups(batch.id)
    assert len(groups) == 2

    by_id = {g.group_id: g for g in groups}
    assert len(by_id["g1"].threads) == 2
    assert len(by_id["g2"].threads) == 1


async def test_create_batch_with_empty_groups(store: SqliteStore) -> None:
    batch = Batch(batch_number=1, category="memories", states=[])
    created = await store.create_batch(batch, [])
    assert created.id == batch.id
    assert await store.get_batch_groups(batch.id) == []


def _make_embedding(seed: float = 1.0) -> list[float]:
    return [seed] + [0.0] * (_TEST_EMBEDDING_DIMS - 1)


def _make_memory(
    content: str = "test memory",
    from_d: date = date(2024, 1, 1),
    to_d: date = date(2024, 1, 5),
    *,
    embedding: list[float] | None = None,
    status: str = MemoryStatus.active.value,
    source_memory_ids: list[str] | None = None,
) -> TapestryMemory:
    return TapestryMemory(
        content=content,
        from_date=from_d,
        to_date=to_d,
        group_id="g1",
        embedding=embedding,
        status=status,
        source_memory_ids=source_memory_ids,
    )


async def test_memory_crud(store: SqliteStore) -> None:
    mem = _make_memory()
    created = await store.create_memory(mem)
    assert created.id == mem.id

    fetched = await store.get_memories([mem.id])
    assert len(fetched) == 1
    assert fetched[0].content == "test memory"

    emb = _make_embedding(0.5)
    mem.embedding = emb
    await store.update_memory(mem)
    updated = await store.get_memories([mem.id])
    assert updated[0].embedding is not None
    assert len(updated[0].embedding) == _TEST_EMBEDDING_DIMS


async def test_get_memories_skips_missing(store: SqliteStore) -> None:
    mem = _make_memory()
    await store.create_memory(mem)
    result = await store.get_memories([mem.id, "nonexistent"])
    assert len(result) == 1


async def test_get_unembedded_memories(store: SqliteStore) -> None:
    m1 = _make_memory(content="no embedding")
    m2 = _make_memory(content="has embedding", embedding=_make_embedding(1.0))
    await store.create_memory(m1)
    await store.create_memory(m2)

    result = await store.get_unembedded_memories([m1.id, m2.id])
    assert len(result) == 1
    assert result[0].id == m1.id


async def test_list_memories_filters(store: SqliteStore) -> None:
    m1 = _make_memory(content="active", from_d=date(2024, 1, 1))
    m2 = _make_memory(
        content="superseded",
        from_d=date(2024, 2, 1),
        status=MemoryStatus.superseded.value,
    )
    m3 = _make_memory(content="active recent", from_d=date(2024, 3, 1))
    await store.create_memory(m1)
    await store.create_memory(m2)
    await store.create_memory(m3)

    active = await store.list_memories(status=MemoryStatus.active.value)
    assert len(active) == 2

    from_feb = await store.list_memories(from_date=date(2024, 2, 1))
    assert len(from_feb) == 2

    limited = await store.list_memories(limit=1)
    assert len(limited) == 1


async def test_count_memories(store: SqliteStore) -> None:
    m1 = _make_memory(status=MemoryStatus.active.value)
    m2 = _make_memory(status=MemoryStatus.superseded.value)
    await store.create_memory(m1)
    await store.create_memory(m2)

    assert await store.count_memories() == 2
    assert await store.count_memories(status=MemoryStatus.active.value) == 1


async def test_search_memories_by_embedding(store: SqliteStore) -> None:
    emb_similar = [1.0] + [0.0] * (_TEST_EMBEDDING_DIMS - 1)
    emb_different = [0.0, 1.0] + [0.0] * (_TEST_EMBEDDING_DIMS - 2)
    m1 = _make_memory(content="similar", embedding=emb_similar)
    m2 = _make_memory(content="different", embedding=emb_different)
    m3 = _make_memory(content="no embed")
    await store.create_memory(m1)
    await store.create_memory(m2)
    await store.create_memory(m3)

    query = [1.0, 0.1] + [0.0] * (_TEST_EMBEDDING_DIMS - 2)
    results = await store.search_memories(query_embedding=query, top_k=2)
    assert len(results) == 2
    assert results[0].content == "similar"
    assert results[0].similarity is not None
    assert results[1].similarity is not None
    assert results[0].similarity > results[1].similarity


async def test_search_memories_by_embedding_with_date_filter(
    store: SqliteStore,
) -> None:
    emb = [1.0] + [0.0] * (_TEST_EMBEDDING_DIMS - 1)
    m1 = _make_memory(
        content="jan", embedding=emb, from_d=date(2024, 1, 1), to_d=date(2024, 1, 31)
    )
    m2 = _make_memory(
        content="feb", embedding=emb, from_d=date(2024, 2, 1), to_d=date(2024, 2, 28)
    )
    m3 = _make_memory(
        content="mar", embedding=emb, from_d=date(2024, 3, 1), to_d=date(2024, 3, 31)
    )
    await store.create_memory(m1)
    await store.create_memory(m2)
    await store.create_memory(m3)

    results = await store.search_memories(
        query_embedding=emb,
        from_date=date(2024, 2, 1),
        to_date=date(2024, 2, 28),
        top_k=10,
    )
    assert len(results) == 1
    assert results[0].content == "feb"
    assert results[0].similarity is not None


async def test_atomic_commits_on_success(store: SqliteStore) -> None:
    async with store.atomic():
        archive = Archive(provider="test")
        await store.create_archive(archive)

    assert await store.get_archive(archive.id) is not None


async def test_atomic_rolls_back_on_error(store: SqliteStore) -> None:
    archive = Archive(provider="test")
    with pytest.raises(RuntimeError):
        async with store.atomic():
            await store.create_archive(archive)
            raise RuntimeError("boom")

    assert await store.get_archive(archive.id) is None


async def test_async_context_manager(tmp_path) -> None:
    s = SqliteStore(path=str(tmp_path / "cm_test.db"))
    await s.init(embedding_dimensions=_TEST_EMBEDDING_DIMS)
    async with s:
        archive = Archive(provider="test")
        await s.create_archive(archive)
        assert await s.get_archive(archive.id) is not None

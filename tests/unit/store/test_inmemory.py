from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from context_use.batch.grouper import ThreadGroup
from context_use.etl.core.types import ThreadRow
from context_use.models import (
    Archive,
    ArchiveStatus,
    Batch,
    EtlTask,
    EtlTaskStatus,
    MemoryStatus,
    TapestryMemory,
    TapestryProfile,
)
from context_use.store.memory import InMemoryStore


@pytest.fixture()
def store() -> InMemoryStore:
    return InMemoryStore()


# ── Lifecycle ────────────────────────────────────────────────────────


async def test_reset_clears_all_data(store: InMemoryStore) -> None:
    archive = Archive(provider="test")
    await store.create_archive(archive)
    assert await store.get_archive(archive.id) is not None

    await store.reset()

    assert await store.get_archive(archive.id) is None


# ── Archives ─────────────────────────────────────────────────────────


async def test_archive_crud(store: InMemoryStore) -> None:
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


async def test_list_archives_filters_by_status(store: InMemoryStore) -> None:
    a1 = Archive(provider="a", status=ArchiveStatus.COMPLETED.value)
    a2 = Archive(provider="b", status=ArchiveStatus.FAILED.value)
    await store.create_archive(a1)
    await store.create_archive(a2)

    completed = await store.list_archives(status=ArchiveStatus.COMPLETED.value)
    assert len(completed) == 1
    assert completed[0].id == a1.id

    all_archives = await store.list_archives()
    assert len(all_archives) == 2


async def test_get_archive_returns_none_for_missing(store: InMemoryStore) -> None:
    assert await store.get_archive("nonexistent") is None


# ── ETL Tasks ────────────────────────────────────────────────────────


async def test_task_crud(store: InMemoryStore) -> None:
    task = EtlTask(
        archive_id="a1",
        provider="chatgpt",
        interaction_type="chatgpt_conversations",
        source_uris=["archive/conversations.json"],
    )
    created = await store.create_task(task)
    assert created.id == task.id

    fetched = await store.get_task(task.id)
    assert fetched is not None
    assert fetched.source_uris == ["archive/conversations.json"]
    assert (
        fetched.source_uri == "archive/conversations.json"
    )  # backward-compat property

    task.status = EtlTaskStatus.COMPLETED.value
    await store.update_task(task)
    updated = await store.get_task(task.id)
    assert updated is not None
    assert updated.status == EtlTaskStatus.COMPLETED.value


async def test_get_tasks_by_archive(store: InMemoryStore) -> None:
    t1 = EtlTask(
        archive_id="a1", provider="p", interaction_type="t", source_uris=["f1"]
    )
    t2 = EtlTask(
        archive_id="a2", provider="p", interaction_type="t", source_uris=["f2"]
    )
    t3 = EtlTask(
        archive_id="a1", provider="p", interaction_type="t", source_uris=["f3"]
    )
    await store.create_task(t1)
    await store.create_task(t2)
    await store.create_task(t3)

    result = await store.get_tasks_by_archive(["a1"])
    assert {t.id for t in result} == {t1.id, t3.id}


# ── Threads ──────────────────────────────────────────────────────────


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


async def test_insert_threads_deduplicates(store: InMemoryStore) -> None:
    rows = [_make_row("k1"), _make_row("k2"), _make_row("k1")]
    count = await store.insert_threads(rows, task_id="t1")
    assert count == 2

    rows2 = [_make_row("k1"), _make_row("k3")]
    count2 = await store.insert_threads(rows2, task_id="t1")
    assert count2 == 1


async def test_get_threads_by_task_ordered_by_asat(store: InMemoryStore) -> None:
    r1 = _make_row("k1", asat=datetime(2024, 3, 1, tzinfo=UTC))
    r2 = _make_row("k2", asat=datetime(2024, 1, 1, tzinfo=UTC))
    r3 = _make_row("k3", asat=datetime(2024, 2, 1, tzinfo=UTC))
    await store.insert_threads([r1, r2, r3], task_id="t1")

    threads = await store.get_threads_by_task(["t1"])
    assert len(threads) == 3
    assert [t.unique_key for t in threads] == ["k2", "k3", "k1"]


async def test_count_threads_for_archive(store: InMemoryStore) -> None:
    task = EtlTask(
        archive_id="a1", provider="p", interaction_type="t", source_uris=["f"]
    )
    await store.create_task(task)
    await store.insert_threads([_make_row("k1"), _make_row("k2")], task_id=task.id)

    assert await store.count_threads_for_archive("a1") == 2
    assert await store.count_threads_for_archive("nonexistent") == 0


# ── Batches ──────────────────────────────────────────────────────────


async def test_batch_crud_with_groups(store: InMemoryStore) -> None:
    await store.insert_threads(
        [_make_row("k1"), _make_row("k2"), _make_row("k3")],
        task_id="t1",
    )
    threads = await store.get_threads_by_task(["t1"])

    group = ThreadGroup(threads=threads[:2], group_id="g1")  # type: ignore[arg-type]
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


async def test_get_batch_groups(store: InMemoryStore) -> None:
    await store.insert_threads(
        [_make_row("k1"), _make_row("k2"), _make_row("k3")],
        task_id="t1",
    )
    threads = await store.get_threads_by_task(["t1"])

    g1 = ThreadGroup(threads=threads[:2], group_id="g1")  # type: ignore[arg-type]
    g2 = ThreadGroup(threads=threads[2:], group_id="g2")  # type: ignore[arg-type]

    batch = Batch(batch_number=1, category="memories", states=[])
    await store.create_batch(batch, [g1, g2])

    groups = await store.get_batch_groups(batch.id)
    assert len(groups) == 2

    by_id = {g.group_id: g for g in groups}
    assert len(by_id["g1"].threads) == 2
    assert len(by_id["g2"].threads) == 1


async def test_create_batch_with_empty_groups(store: InMemoryStore) -> None:
    batch = Batch(batch_number=1, category="refinement", states=[])
    created = await store.create_batch(batch, [])
    assert created.id == batch.id
    assert await store.get_batch_groups(batch.id) == []


# ── Memories ─────────────────────────────────────────────────────────


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


async def test_memory_crud(store: InMemoryStore) -> None:
    mem = _make_memory()
    created = await store.create_memory(mem)
    assert created.id == mem.id

    fetched = await store.get_memories([mem.id])
    assert len(fetched) == 1
    assert fetched[0].content == "test memory"

    mem.embedding = [0.1, 0.2, 0.3]
    await store.update_memory(mem)
    updated = await store.get_memories([mem.id])
    assert updated[0].embedding == [0.1, 0.2, 0.3]


async def test_get_memories_skips_missing(store: InMemoryStore) -> None:
    mem = _make_memory()
    await store.create_memory(mem)
    result = await store.get_memories([mem.id, "nonexistent"])
    assert len(result) == 1


async def test_get_unembedded_memories(store: InMemoryStore) -> None:
    m1 = _make_memory(content="no embedding")
    m2 = _make_memory(content="has embedding", embedding=[1.0, 0.0])
    await store.create_memory(m1)
    await store.create_memory(m2)

    result = await store.get_unembedded_memories([m1.id, m2.id])
    assert len(result) == 1
    assert result[0].id == m1.id


async def test_list_memories_filters(store: InMemoryStore) -> None:
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


async def test_count_memories(store: InMemoryStore) -> None:
    m1 = _make_memory(status=MemoryStatus.active.value)
    m2 = _make_memory(status=MemoryStatus.superseded.value)
    await store.create_memory(m1)
    await store.create_memory(m2)

    assert await store.count_memories() == 2
    assert await store.count_memories(status=MemoryStatus.active.value) == 1


async def test_search_memories_by_date(store: InMemoryStore) -> None:
    m1 = _make_memory(content="jan", from_d=date(2024, 1, 1), to_d=date(2024, 1, 31))
    m2 = _make_memory(content="feb", from_d=date(2024, 2, 1), to_d=date(2024, 2, 28))
    m3 = _make_memory(content="mar", from_d=date(2024, 3, 1), to_d=date(2024, 3, 31))
    await store.create_memory(m1)
    await store.create_memory(m2)
    await store.create_memory(m3)

    results = await store.search_memories(
        from_date=date(2024, 2, 1), to_date=date(2024, 2, 28), top_k=10
    )
    assert len(results) == 1
    assert results[0].content == "feb"
    assert results[0].similarity is None


async def test_search_memories_by_embedding(store: InMemoryStore) -> None:
    m1 = _make_memory(content="similar", embedding=[1.0, 0.0, 0.0])
    m2 = _make_memory(content="different", embedding=[0.0, 1.0, 0.0])
    m3 = _make_memory(content="no embed")
    await store.create_memory(m1)
    await store.create_memory(m2)
    await store.create_memory(m3)

    results = await store.search_memories(query_embedding=[1.0, 0.1, 0.0], top_k=2)
    assert len(results) == 2
    assert results[0].content == "similar"
    assert results[0].similarity is not None
    assert results[0].similarity > results[1].similarity  # type: ignore[operator]


async def test_get_refinable_memory_ids(store: InMemoryStore) -> None:
    m1 = _make_memory(embedding=[1.0])
    m2 = _make_memory()  # no embedding
    m3 = _make_memory(embedding=[1.0], source_memory_ids=["other"])  # already refined
    m4 = _make_memory(
        embedding=[1.0], status=MemoryStatus.superseded.value
    )  # superseded
    await store.create_memory(m1)
    await store.create_memory(m2)
    await store.create_memory(m3)
    await store.create_memory(m4)

    ids = await store.get_refinable_memory_ids()
    assert ids == [m1.id]


async def test_find_similar_memories(store: InMemoryStore) -> None:
    seed = _make_memory(
        content="seed",
        from_d=date(2024, 1, 1),
        to_d=date(2024, 1, 5),
        embedding=[1.0, 0.0, 0.0],
    )
    close = _make_memory(
        content="close",
        from_d=date(2024, 1, 3),
        to_d=date(2024, 1, 8),
        embedding=[0.9, 0.1, 0.0],
    )
    far_date = _make_memory(
        content="far date",
        from_d=date(2024, 6, 1),
        to_d=date(2024, 6, 5),
        embedding=[0.9, 0.1, 0.0],
    )
    orthogonal = _make_memory(
        content="orthogonal",
        from_d=date(2024, 1, 1),
        to_d=date(2024, 1, 5),
        embedding=[0.0, 1.0, 0.0],
    )
    await store.create_memory(seed)
    await store.create_memory(close)
    await store.create_memory(far_date)
    await store.create_memory(orthogonal)

    similar = await store.find_similar_memories(
        seed.id, date_proximity_days=7, similarity_threshold=0.4
    )
    assert close.id in similar
    assert far_date.id not in similar  # outside date range
    assert orthogonal.id not in similar  # too dissimilar


async def test_find_similar_memories_missing_seed(store: InMemoryStore) -> None:
    assert await store.find_similar_memories("nonexistent") == []


# ── Profiles ─────────────────────────────────────────────────────────


async def test_profile_save_and_get_latest(store: InMemoryStore) -> None:
    assert await store.get_latest_profile() is None

    p1 = TapestryProfile(
        content="old",
        generated_at=datetime(2024, 1, 1, tzinfo=UTC),
        memory_count=5,
    )
    await store.save_profile(p1)
    assert (await store.get_latest_profile()) is not None

    p2 = TapestryProfile(
        content="new",
        generated_at=datetime(2024, 6, 1, tzinfo=UTC),
        memory_count=10,
    )
    await store.save_profile(p2)

    latest = await store.get_latest_profile()
    assert latest is not None
    assert latest.content == "new"


# ── atomic() ─────────────────────────────────────────────────────────


async def test_atomic_is_noop(store: InMemoryStore) -> None:
    async with store.atomic():
        archive = Archive(provider="test")
        await store.create_archive(archive)

    assert await store.get_archive(archive.id) is not None


# ── Context manager ──────────────────────────────────────────────────


async def test_async_context_manager() -> None:
    async with InMemoryStore() as store:
        archive = Archive(provider="test")
        await store.create_archive(archive)
        assert await store.get_archive(archive.id) is not None

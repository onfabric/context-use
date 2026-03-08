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


async def test_get_unprocessed_threads_ordered_by_asat(store: InMemoryStore) -> None:
    r1 = _make_row("k1", asat=datetime(2024, 3, 1, tzinfo=UTC))
    r2 = _make_row("k2", asat=datetime(2024, 1, 1, tzinfo=UTC))
    r3 = _make_row("k3", asat=datetime(2024, 2, 1, tzinfo=UTC))
    await store.insert_threads([r1, r2, r3], task_id="t1")

    threads = await store.get_unprocessed_threads()
    assert len(threads) == 3
    assert [t.unique_key for t in threads] == ["k2", "k3", "k1"]


async def test_get_unprocessed_threads_excludes_batched(store: InMemoryStore) -> None:
    await store.insert_threads(
        [_make_row("k1"), _make_row("k2"), _make_row("k3")], task_id="t1"
    )
    all_threads = await store.get_unprocessed_threads()

    group = ThreadGroup(threads=all_threads[:1], group_id="g1")  # type: ignore[arg-type]
    batch = Batch(batch_number=1, category="memories", states=[])
    await store.create_batch(batch, [group])

    remaining = await store.get_unprocessed_threads()
    assert len(remaining) == 2
    assert all_threads[0].id not in {t.id for t in remaining}


async def test_get_unprocessed_threads_interaction_type_filter(
    store: InMemoryStore,
) -> None:
    await store.insert_threads(
        [
            _make_row("k1", interaction_type="type_a"),
            _make_row("k2", interaction_type="type_b"),
            _make_row("k3", interaction_type="type_a"),
        ],
        task_id="t1",
    )

    threads = await store.get_unprocessed_threads(interaction_types=["type_a"])
    assert len(threads) == 2
    assert all(t.interaction_type == "type_a" for t in threads)


# ── Batches ──────────────────────────────────────────────────────────


async def test_batch_crud_with_groups(store: InMemoryStore) -> None:
    await store.insert_threads(
        [_make_row("k1"), _make_row("k2"), _make_row("k3")],
        task_id="t1",
    )
    threads = await store.get_unprocessed_threads()

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
    threads = await store.get_unprocessed_threads()

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
    batch = Batch(batch_number=1, category="memories", states=[])
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


# ── User Profile ──────────────────────────────────────────────────────


async def test_user_profile_returns_none_when_empty(store: InMemoryStore) -> None:
    assert await store.get_user_profile() is None


async def test_user_profile_upsert_creates(store: InMemoryStore) -> None:
    from context_use.models.user_profile import UserProfile

    profile = UserProfile(content="# My Profile\nI am a developer.")
    saved = await store.upsert_user_profile(profile)
    assert saved.content == "# My Profile\nI am a developer."

    fetched = await store.get_user_profile()
    assert fetched is not None
    assert fetched.content == "# My Profile\nI am a developer."


async def test_user_profile_upsert_updates(store: InMemoryStore) -> None:
    from context_use.models.user_profile import UserProfile

    first = UserProfile(content="v1")
    await store.upsert_user_profile(first)

    second = UserProfile(content="v2")
    updated = await store.upsert_user_profile(second)
    assert updated.content == "v2"

    fetched = await store.get_user_profile()
    assert fetched is not None
    assert fetched.content == "v2"


async def test_user_profile_upsert_preserves_created_at(store: InMemoryStore) -> None:
    from context_use.models.user_profile import UserProfile

    first = UserProfile(content="v1")
    saved = await store.upsert_user_profile(first)
    original_created = saved.created_at

    second = UserProfile(content="v2")
    updated = await store.upsert_user_profile(second)
    assert updated.created_at == original_created


async def test_reset_clears_user_profile(store: InMemoryStore) -> None:
    from context_use.models.user_profile import UserProfile

    await store.upsert_user_profile(UserProfile(content="profile"))
    assert await store.get_user_profile() is not None

    await store.reset()
    assert await store.get_user_profile() is None

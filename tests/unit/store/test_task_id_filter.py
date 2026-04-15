from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from context_use.etl.core.types import ThreadRow
from context_use.models import Archive, EtlTask
from context_use.models.batch import BatchCategory
from context_use.store.sqlite import SqliteStore

EMBEDDING_DIMS = 256


def _make_row(
    *,
    key: str,
    interaction_type: str = "instagram_posts",
    asat: datetime | None = None,
) -> ThreadRow:
    return ThreadRow(
        unique_key=key,
        provider="Instagram",
        interaction_type=interaction_type,
        preview="preview",
        payload={"type": "Create"},
        version="1.0.0",
        asat=asat or datetime(2025, 1, 1, tzinfo=UTC),
    )


async def _create_task(store: SqliteStore, task_id: str) -> str:
    archive = await store.create_archive(
        Archive(provider="Instagram", status="created")
    )
    task = EtlTask(
        id=task_id,
        archive_id=archive.id,
        provider="Instagram",
        interaction_type="instagram_posts",
        source_uris=["file.json"],
    )
    await store.create_task(task)
    return task_id


@pytest.fixture()
async def store(tmp_path: Path) -> SqliteStore:
    s = SqliteStore(path=str(tmp_path / "test.db"))
    await s.init(embedding_dimensions=EMBEDDING_DIMS)
    return s


class TestGetUnprocessedThreadsTaskIdFilter:
    @pytest.mark.asyncio
    async def test_returns_only_threads_for_given_task(
        self, store: SqliteStore
    ) -> None:
        await _create_task(store, "task-A")
        await _create_task(store, "task-B")
        await store.insert_threads(
            [_make_row(key="a1"), _make_row(key="a2")], task_id="task-A"
        )
        await store.insert_threads([_make_row(key="b1")], task_id="task-B")

        result = await store.get_unprocessed_threads(task_id="task-A")
        keys = {t.unique_key for t in result}
        assert keys == {"a1", "a2"}

    @pytest.mark.asyncio
    async def test_returns_all_when_task_id_is_none(self, store: SqliteStore) -> None:
        await _create_task(store, "task-A")
        await _create_task(store, "task-B")
        await store.insert_threads([_make_row(key="a1")], task_id="task-A")
        await store.insert_threads([_make_row(key="b1")], task_id="task-B")

        result = await store.get_unprocessed_threads(task_id=None)
        keys = {t.unique_key for t in result}
        assert keys == {"a1", "b1"}

    @pytest.mark.asyncio
    async def test_task_id_combined_with_batch_category(
        self, store: SqliteStore
    ) -> None:
        await _create_task(store, "task-A")
        await _create_task(store, "task-B")
        await store.insert_threads(
            [_make_row(key="a1"), _make_row(key="a2")], task_id="task-A"
        )
        await store.insert_threads([_make_row(key="b1")], task_id="task-B")

        result = await store.get_unprocessed_threads(
            batch_category=BatchCategory.asset_description.value,
            task_id="task-A",
        )
        keys = {t.unique_key for t in result}
        assert keys == {"a1", "a2"}

    @pytest.mark.asyncio
    async def test_returns_empty_for_nonexistent_task(self, store: SqliteStore) -> None:
        await _create_task(store, "task-A")
        await store.insert_threads([_make_row(key="a1")], task_id="task-A")

        result = await store.get_unprocessed_threads(task_id="no-such-task")
        assert result == []

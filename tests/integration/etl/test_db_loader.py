from __future__ import annotations

import datetime
from collections.abc import AsyncGenerator, Iterator

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_use.db.postgres import PostgresBackend
from context_use.etl.core.loader import DbLoader
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.models.archive import Archive, ArchiveStatus
from context_use.etl.models.etl_task import EtlTask as OrmEtlTask
from context_use.etl.models.etl_task import EtlTaskStatus
from context_use.etl.models.thread import Thread
from context_use.models.etl_task import EtlTask
from context_use.storage.base import StorageBackend


class _MockRecord(BaseModel):
    role: str
    content: str


_MOCK_PAYLOAD_VERSION = "1.0.0"


class _MockPipe(Pipe[_MockRecord]):
    provider = "test"
    interaction_type = "test_conversations"
    archive_version = "v1"
    archive_path_pattern = "conversations.json"
    record_schema = _MockRecord

    def extract(self, task: EtlTask, storage: StorageBackend) -> Iterator[_MockRecord]:
        yield _MockRecord(role="user", content="hello")
        yield _MockRecord(role="assistant", content="world")

    def transform(self, record: _MockRecord, task: EtlTask) -> ThreadRow:
        return ThreadRow(
            unique_key=f"mock:{record.content}",
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=record.content,
            payload={"role": record.role, "text": record.content},
            version=_MOCK_PAYLOAD_VERSION,
            asat=datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC),
        )


type TaskWithSession = tuple[OrmEtlTask, AsyncSession]


@pytest.fixture()
async def task_with_session(db: PostgresBackend) -> AsyncGenerator[TaskWithSession]:
    async with db.session_scope() as s:
        archive = Archive(provider="test", status=ArchiveStatus.CREATED.value)
        s.add(archive)
        await s.flush()

        etl_task = OrmEtlTask(
            archive_id=archive.id,
            provider="test",
            interaction_type="test_conversations",
            source_uri="conversations.json",
            status=EtlTaskStatus.CREATED.value,
        )
        etl_task.archive = archive
        s.add(etl_task)
        await s.flush()

        yield etl_task, s


class TestDbLoader:
    async def test_load_inserts_rows(self, task_with_session: TaskWithSession):
        task, session = task_with_session

        pipe = _MockPipe()
        rows = list(pipe.run(task, storage=None))  # type: ignore[arg-type]

        loader = DbLoader(session=session)
        count = await loader.load(rows, task)
        assert count == 2

        result = await session.execute(select(Thread))
        threads = result.scalars().all()
        assert len(threads) == 2

        for thread in threads:
            assert thread.provider == "test"
            assert thread.interaction_type == "test_conversations"
            assert thread.etl_task_id == task.id
            assert thread.version == _MOCK_PAYLOAD_VERSION
            assert thread.preview in ("hello", "world")

    async def test_load_deduplicates(self, task_with_session: TaskWithSession):
        task, session = task_with_session

        pipe = _MockPipe()
        rows = list(pipe.run(task, storage=None))  # type: ignore[arg-type]

        loader = DbLoader(session=session)

        count1 = await loader.load(rows, task)
        assert count1 == 2
        await session.flush()

        count2 = await loader.load(rows, task)
        assert count2 == 0

        result = await session.execute(select(Thread))
        threads = result.scalars().all()
        assert len(threads) == 2

    async def test_load_accepts_iterator(self, task_with_session: TaskWithSession):
        """DbLoader.load() should accept any Iterable, including a lazy iterator."""
        task, session = task_with_session

        pipe = _MockPipe()
        loader = DbLoader(session=session)
        count = await loader.load(pipe.run(task, storage=None), task)  # type: ignore[arg-type]
        assert count == 2

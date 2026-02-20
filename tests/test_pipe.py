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
from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.etl.models.thread import Thread
from context_use.storage.base import StorageBackend


class MockRecord(BaseModel):
    role: str
    content: str


MOCK_PAYLOAD_VERSION = "1.0.0"


class MockPipe(Pipe[MockRecord]):
    provider = "test"
    interaction_type = "test_conversations"
    archive_version = "v1"
    archive_path = "conversations.json"
    record_schema = MockRecord

    def extract(self, task: EtlTask, storage: StorageBackend) -> Iterator[MockRecord]:
        yield MockRecord(role="user", content="hello")
        yield MockRecord(role="assistant", content="world")

    def transform(self, record: MockRecord, task: EtlTask) -> ThreadRow:
        return ThreadRow(
            unique_key=f"mock:{record.content}",
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=record.content,
            payload={"role": record.role, "text": record.content},
            version=MOCK_PAYLOAD_VERSION,
            asat=datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC),
        )


class DroppingPipe(Pipe[MockRecord]):
    """A pipe whose transform() returns None for some records."""

    provider = "test"
    interaction_type = "test_conversations"
    archive_version = "v1"
    archive_path = "conversations.json"
    record_schema = MockRecord

    def extract(self, task: EtlTask, storage: StorageBackend) -> Iterator[MockRecord]:
        yield MockRecord(role="user", content="keep-me")
        yield MockRecord(role="system", content="drop-me")
        yield MockRecord(role="assistant", content="also-keep")

    def transform(self, record: MockRecord, task: EtlTask) -> ThreadRow | None:  # type: ignore[override]
        if record.role == "system":
            return None
        return ThreadRow(
            unique_key=f"mock:{record.content}",
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=record.content,
            payload={"role": record.role, "text": record.content},
            version=MOCK_PAYLOAD_VERSION,
            asat=datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC),
        )


type TaskWithSession = tuple[EtlTask, AsyncSession]


@pytest.fixture()
async def task_with_session(db: PostgresBackend) -> AsyncGenerator[TaskWithSession]:
    async with db.session_scope() as s:
        archive = Archive(provider="test", status=ArchiveStatus.CREATED.value)
        s.add(archive)
        await s.flush()

        etl_task = EtlTask(
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


class TestThreadRow:
    def test_required_fields(self):
        row = ThreadRow(
            unique_key="uk",
            provider="chatgpt",
            interaction_type="chatgpt_conversations",
            preview="hi",
            payload={"text": "hi"},
            version="1.0.0",
            asat=datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC),
        )
        assert row.unique_key == "uk"
        assert row.source is None
        assert row.asset_uri is None

    def test_optional_fields(self):
        row = ThreadRow(
            unique_key="uk",
            provider="instagram",
            interaction_type="instagram_stories",
            preview="Story",
            payload={"media": "photo.jpg"},
            version="1.0.0",
            asat=datetime.datetime(2025, 6, 15, tzinfo=datetime.UTC),
            source="stories.json",
            asset_uri="staging/abc/photo.jpg",
        )
        assert row.source == "stories.json"
        assert row.asset_uri == "staging/abc/photo.jpg"


class TestPipe:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):

            class IncompletePipe(Pipe[MockRecord]):
                provider = "test"
                interaction_type = "test"
                archive_version = "v1"
                archive_path = "data.json"
                record_schema = MockRecord

                # Missing extract and transform
                pass

            IncompletePipe()  # type: ignore[reportAbstractUsage]

    def test_run_yields_thread_rows(self):
        pipe = MockPipe()
        # task and storage are not used by MockPipe in a meaningful way,
        # but we still need valid-looking objects.
        task = EtlTask(
            archive_id="fake",
            provider="test",
            interaction_type="test_conversations",
            source_uri="conversations.json",
        )
        rows = list(pipe.run(task, storage=None))  # type: ignore[arg-type]

        assert len(rows) == 2
        assert all(isinstance(r, ThreadRow) for r in rows)
        assert rows[0].unique_key == "mock:hello"
        assert rows[1].unique_key == "mock:world"
        assert rows[0].provider == "test"
        assert rows[0].version == MOCK_PAYLOAD_VERSION

    def test_run_tracks_counts(self):
        pipe = MockPipe()
        task = EtlTask(
            archive_id="fake",
            provider="test",
            interaction_type="test_conversations",
            source_uri="conversations.json",
        )
        # Must consume the iterator for counts to be final
        rows = list(pipe.run(task, storage=None))  # type: ignore[arg-type]

        assert pipe.extracted_count == 2
        assert pipe.transformed_count == 2
        assert len(rows) == 2

    def test_run_counts_diverge_when_transform_drops(self):
        """extracted_count > transformed_count when transform() returns None."""
        pipe = DroppingPipe()
        task = EtlTask(
            archive_id="fake",
            provider="test",
            interaction_type="test_conversations",
            source_uri="conversations.json",
        )
        rows = list(pipe.run(task, storage=None))  # type: ignore[arg-type]

        assert pipe.extracted_count == 3
        assert pipe.transformed_count == 2
        assert len(rows) == 2

    def test_class_vars_accessible(self):
        assert MockPipe.provider == "test"
        assert MockPipe.interaction_type == "test_conversations"
        assert MockPipe.archive_version == "v1"
        assert MockPipe.archive_path == "conversations.json"
        assert MockPipe.record_schema is MockRecord


class TestDbLoader:
    async def test_load_inserts_rows(self, task_with_session: TaskWithSession):
        task, session = task_with_session

        pipe = MockPipe()
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
            assert thread.version == MOCK_PAYLOAD_VERSION
            assert thread.preview in ("hello", "world")

    async def test_load_deduplicates(self, task_with_session: TaskWithSession):
        task, session = task_with_session

        pipe = MockPipe()
        rows = list(pipe.run(task, storage=None))  # type: ignore[arg-type]

        loader = DbLoader(session=session)

        count1 = await loader.load(rows, task)
        assert count1 == 2
        await session.flush()

        # Same rows again — should be deduplicated
        count2 = await loader.load(rows, task)
        assert count2 == 0

        result = await session.execute(select(Thread))
        threads = result.scalars().all()
        assert len(threads) == 2

    async def test_load_accepts_iterator(self, task_with_session: TaskWithSession):
        """DbLoader.load() should accept any Iterable, including a lazy iterator."""
        task, session = task_with_session

        pipe = MockPipe()
        # Pass the generator directly — not materialised into a list
        loader = DbLoader(session=session)
        count = await loader.load(pipe.run(task, storage=None), task)  # type: ignore[arg-type]
        assert count == 2

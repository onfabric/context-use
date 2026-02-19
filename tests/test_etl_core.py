from __future__ import annotations

import datetime
from collections.abc import AsyncGenerator
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_use.db.postgres import PostgresBackend
from context_use.etl.core.etl import (
    ETLPipeline,
    ExtractionStrategy,
    OrchestrationStrategy,
    TransformStrategy,
    UploadStrategy,
)
from context_use.etl.core.exceptions import (
    ExtractionFailedException,
    TransformFailedException,
)
from context_use.etl.models.archive import Archive, ArchiveStatus
from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.etl.models.thread import Thread
from context_use.storage.disk import DiskStorage


class MockExtraction(ExtractionStrategy):
    def extract(self, task, storage):
        return [
            pd.DataFrame(
                [
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "hello"},
                ]
            )
        ]


class MockTransform(TransformStrategy):
    def transform(self, task, batches):
        rows = []
        for df in batches:
            for _, r in df.iterrows():
                rows.append(
                    {
                        "unique_key": f"mock:{r['content']}",
                        "provider": task.provider,
                        "interaction_type": task.interaction_type,
                        "preview": r["content"],
                        "payload": {"text": r["content"]},
                        "source": None,
                        "version": "1.0.0",
                        "asat": datetime.datetime.now(datetime.UTC),
                        "asset_uri": None,
                    }
                )
        return [pd.DataFrame(rows)]


class FailingExtraction(ExtractionStrategy):
    def extract(self, task, storage):
        raise RuntimeError("boom")


class FailingTransform(TransformStrategy):
    def transform(self, task, batches):
        raise RuntimeError("kaboom")


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
            interaction_type="test_type",
            source_uri="test.json",
            status=EtlTaskStatus.CREATED.value,
        )
        etl_task.archive = archive
        s.add(etl_task)
        await s.flush()

        yield etl_task, s


class TestETLPipeline:
    async def test_full_run(self, tmp_path: Path, task_with_session: TaskWithSession):
        task, session = task_with_session
        storage = DiskStorage(str(tmp_path / "s"))

        pipeline = ETLPipeline(
            extraction=MockExtraction(),
            transform=MockTransform(),
            upload=UploadStrategy(),
            storage=storage,
            session=session,
        )
        count = await pipeline.run(task)
        assert count == 2

    async def test_extract_failure(
        self, tmp_path: Path, task_with_session: TaskWithSession
    ):
        task, _ = task_with_session
        storage = DiskStorage(str(tmp_path / "s"))

        pipeline = ETLPipeline(
            extraction=FailingExtraction(),
            transform=MockTransform(),
            storage=storage,
        )
        with pytest.raises(ExtractionFailedException):
            await pipeline.run(task)

    async def test_transform_failure(
        self, tmp_path: Path, task_with_session: TaskWithSession
    ):
        task, _ = task_with_session
        storage = DiskStorage(str(tmp_path / "s"))

        pipeline = ETLPipeline(
            extraction=MockExtraction(),
            transform=FailingTransform(),
            storage=storage,
        )
        with pytest.raises(TransformFailedException):
            await pipeline.run(task)

    async def test_upload_skips_duplicates(
        self, tmp_path: Path, task_with_session: TaskWithSession
    ):
        """Re-uploading the same threads should skip duplicates and not error."""
        task, session = task_with_session
        storage = DiskStorage(str(tmp_path / "s"))

        pipeline = ETLPipeline(
            extraction=MockExtraction(),
            transform=MockTransform(),
            upload=UploadStrategy(),
            storage=storage,
            session=session,
        )

        # First run: both rows inserted
        count1 = await pipeline.run(task)
        assert count1 == 2
        await session.flush()

        # Second run with same data: duplicates skipped
        count2 = await pipeline.run(task)
        assert count2 == 0
        await session.flush()

        # Only 2 threads in the DB, not 4
        result = await session.execute(select(Thread))
        threads = result.scalars().all()
        assert len(threads) == 2


class TestOrchestrationStrategy:
    def test_discover(self):
        class TestOrch(OrchestrationStrategy):
            MANIFEST_MAP = {"data.json": "test_task"}

        orch = TestOrch()
        tasks = orch.discover_tasks("a1", ["a1/data.json", "a1/other.txt"], "test")
        assert len(tasks) == 1
        assert isinstance(tasks[0], EtlTask)
        assert tasks[0].interaction_type == "test_task"
        assert tasks[0].source_uri == "a1/data.json"
        assert tasks[0].provider == "test"
        assert tasks[0].archive_id == "a1"

    def test_discover_ignores_suffix_match(self):
        """shared_conversations.json should NOT match conversations.json."""

        class TestOrch(OrchestrationStrategy):
            MANIFEST_MAP = {"conversations.json": "chatgpt_conversations"}

        orch = TestOrch()
        tasks = orch.discover_tasks(
            "a1",
            ["a1/conversations.json", "a1/shared_conversations.json"],
            "chatgpt",
        )
        assert len(tasks) == 1
        assert tasks[0].source_uri == "a1/conversations.json"

    def test_discover_empty(self):
        class TestOrch(OrchestrationStrategy):
            MANIFEST_MAP = {"data.json": "test_task"}

        orch = TestOrch()
        tasks = orch.discover_tasks("a1", ["a1/other.txt"], "test")
        assert tasks == []

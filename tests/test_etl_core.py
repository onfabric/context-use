"""Unit tests for ETL pipeline with mock strategies."""

from __future__ import annotations

import datetime

import pandas as pd
import pytest
from pydantic import BaseModel

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
from context_use.etl.core.types import ExtractedBatch
from context_use.etl.models.archive import Archive, ArchiveStatus
from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.etl.models.thread import Thread
from context_use.storage.disk import DiskStorage


class MockRecord(BaseModel):
    role: str
    content: str


class MockExtraction(ExtractionStrategy):
    record_schema = MockRecord  # type: ignore[reportAssignmentType]

    def extract(self, task, storage):
        return [
            ExtractedBatch(
                records=[
                    MockRecord(role="user", content="hi"),
                    MockRecord(role="assistant", content="hello"),
                ]
            )
        ]


class MockTransform(TransformStrategy):
    record_schema = MockRecord  # type: ignore[reportAssignmentType]

    def transform(self, task, batches):
        rows = []
        for batch in batches:
            for record in batch.records:
                rows.append(
                    {
                        "unique_key": f"mock:{record.content}",
                        "provider": task.provider,
                        "interaction_type": task.interaction_type,
                        "preview": record.content,
                        "payload": {"text": record.content},
                        "source": None,
                        "version": "1.0.0",
                        "asat": datetime.datetime.now(datetime.UTC),
                        "asset_uri": None,
                    }
                )
        return [pd.DataFrame(rows)]


class FailingExtraction(ExtractionStrategy):
    record_schema = MockRecord  # type: ignore[reportAssignmentType]

    def extract(self, task, storage):
        raise RuntimeError("boom")


class FailingTransform(TransformStrategy):
    record_schema = MockRecord  # type: ignore[reportAssignmentType]

    def transform(self, task, batches):
        raise RuntimeError("kaboom")


class OtherRecord(BaseModel):
    value: int


class MismatchedTransform(TransformStrategy):
    record_schema = OtherRecord  # type: ignore[reportAssignmentType]

    def transform(self, task, batches):
        return []


@pytest.fixture()
def task_with_session(db: PostgresBackend):
    with db.session_scope() as s:
        archive = Archive(provider="test", status=ArchiveStatus.CREATED.value)
        s.add(archive)
        s.flush()

        etl_task = EtlTask(
            archive_id=archive.id,
            provider="test",
            interaction_type="test_type",
            source_uri="test.json",
            status=EtlTaskStatus.CREATED.value,
        )
        s.add(etl_task)
        s.flush()

        yield etl_task, s


class TestETLPipeline:
    def test_full_run(self, tmp_path, task_with_session):
        task, session = task_with_session
        storage = DiskStorage(str(tmp_path / "s"))

        pipeline = ETLPipeline(
            extraction=MockExtraction(),
            transform=MockTransform(),
            upload=UploadStrategy(),
            storage=storage,
            session=session,
        )
        count = pipeline.run(task)
        assert count == 2

    def test_extract_failure(self, tmp_path, task_with_session):
        task, _ = task_with_session
        storage = DiskStorage(str(tmp_path / "s"))

        pipeline = ETLPipeline(
            extraction=FailingExtraction(),
            transform=MockTransform(),
            storage=storage,
        )
        with pytest.raises(ExtractionFailedException):
            pipeline.run(task)

    def test_transform_failure(self, tmp_path, task_with_session):
        task, _ = task_with_session
        storage = DiskStorage(str(tmp_path / "s"))

        pipeline = ETLPipeline(
            extraction=MockExtraction(),
            transform=FailingTransform(),
            storage=storage,
        )
        with pytest.raises(TransformFailedException):
            pipeline.run(task)

    def test_upload_skips_duplicates(self, tmp_path, task_with_session):
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
        count1 = pipeline.run(task)
        assert count1 == 2
        session.flush()

        # Second run with same data: duplicates skipped
        count2 = pipeline.run(task)
        assert count2 == 0
        session.flush()

        # Only 2 threads in the DB, not 4
        threads = session.query(Thread).all()
        assert len(threads) == 2

    def test_schema_mismatch_raises(self, tmp_path):
        """Pairing E and T with different record_schema should raise TypeError."""
        with pytest.raises(TypeError, match="Schema mismatch"):
            ETLPipeline(
                extraction=MockExtraction(),
                transform=MismatchedTransform(),
            )

    def test_missing_record_schema_raises(self):
        """Forgetting record_schema should raise TypeError at instantiation."""
        with pytest.raises(TypeError, match="abstract method"):

            class BadExtraction(ExtractionStrategy):
                def extract(self, task, storage):
                    return []

            BadExtraction()  # type: ignore[reportAbstractUsage]


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

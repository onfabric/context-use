"""Unit tests for ETL pipeline with mock strategies."""

from __future__ import annotations

import datetime

import pandas as pd
import pytest

from contextuse.core.etl import (
    ETLPipeline,
    ExtractionStrategy,
    OrchestrationStrategy,
    TransformStrategy,
    UploadStrategy,
)
from contextuse.core.exceptions import (
    ExtractionFailedException,
    TransformFailedException,
)
from contextuse.core.types import TaskMetadata
from contextuse.db.sqlite import SQLiteBackend
from contextuse.storage.disk import DiskStorage


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
                        "asat": datetime.datetime.now(datetime.timezone.utc),
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


@pytest.fixture()
def task():
    return TaskMetadata(
        archive_id="a1",
        etl_task_id="t1",
        provider="test",
        interaction_type="test_type",
        filenames=["test.json"],
    )


class TestETLPipeline:
    def test_full_run(self, tmp_path, task):
        storage = DiskStorage(str(tmp_path / "s"))
        db = SQLiteBackend(":memory:")
        db.init_db()

        pipeline = ETLPipeline(
            extraction=MockExtraction(),
            transform=MockTransform(),
            upload=UploadStrategy(),
            storage=storage,
            db=db,
        )
        count = pipeline.run(task)
        assert count == 2

    def test_extract_failure(self, tmp_path, task):
        storage = DiskStorage(str(tmp_path / "s"))
        db = SQLiteBackend(":memory:")
        db.init_db()

        pipeline = ETLPipeline(
            extraction=FailingExtraction(),
            transform=MockTransform(),
            storage=storage,
            db=db,
        )
        with pytest.raises(ExtractionFailedException):
            pipeline.run(task)

    def test_transform_failure(self, tmp_path, task):
        storage = DiskStorage(str(tmp_path / "s"))
        db = SQLiteBackend(":memory:")
        db.init_db()

        pipeline = ETLPipeline(
            extraction=MockExtraction(),
            transform=FailingTransform(),
            storage=storage,
            db=db,
        )
        with pytest.raises(TransformFailedException):
            pipeline.run(task)


class TestOrchestrationStrategy:
    def test_discover(self):
        class TestOrch(OrchestrationStrategy):
            MANIFEST_MAP = {"data.json": "test_task"}

        orch = TestOrch()
        tasks = orch.discover_tasks("a1", ["a1/data.json", "a1/other.txt"])
        assert len(tasks) == 1
        assert tasks[0]["interaction_type"] == "test_task"
        assert tasks[0]["filenames"] == ["a1/data.json"]

    def test_discover_ignores_suffix_match(self):
        """shared_conversations.json should NOT match conversations.json."""

        class TestOrch(OrchestrationStrategy):
            MANIFEST_MAP = {"conversations.json": "chatgpt_conversations"}

        orch = TestOrch()
        tasks = orch.discover_tasks(
            "a1",
            ["a1/conversations.json", "a1/shared_conversations.json"],
        )
        assert len(tasks) == 1
        assert tasks[0]["filenames"] == ["a1/conversations.json"]

    def test_discover_empty(self):
        class TestOrch(OrchestrationStrategy):
            MANIFEST_MAP = {"data.json": "test_task"}

        orch = TestOrch()
        tasks = orch.discover_tasks("a1", ["a1/other.txt"])
        assert tasks == []


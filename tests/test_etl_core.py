from datetime import datetime, UTC
from pathlib import Path

import pandas as pd
import pytest

from context_use.db.sqlite import SQLiteBackend
from context_use.modules.etl.core.base import (
    ETLPipeline,
    ExtractionStrategy,
    OrchestrationStrategy,
    TransformStrategy,
    UploadStrategy,
)
from context_use.modules.etl.core.exceptions import (
    ExtractionFailedException,
    TransformFailedException,
)
from context_use.modules.etl.core.types import TaskMetadata
from context_use.storage.disk import DiskStorage


def _make_task() -> TaskMetadata:
    return TaskMetadata(
        archive_id="archive-1",
        etl_task_id="task-1",
        provider="test",
        interaction_type="messages",
        filenames=["archive-1/messages.json"],
    )


class MockExtraction(ExtractionStrategy):
    def extract(self, task, storage):
        return [
            pd.DataFrame(
                [
                    {"text": "hello", "ts": "2025-01-01T00:00:00Z"},
                    {"text": "world", "ts": "2025-01-02T00:00:00Z"},
                ]
            )
        ]


class MockTransform(TransformStrategy):
    def transform(self, task, batches):
        now = datetime.now(UTC)
        rows = []
        for df in batches:
            for _, row in df.iterrows():
                rows.append(
                    {
                        "unique_key": f"{task.provider}_{row['text']}",
                        "provider": task.provider,
                        "interaction_type": task.interaction_type,
                        "preview": row["text"],
                        "payload": {"type": "Note", "content": row["text"]},
                        "source": None,
                        "version": "1.0.0",
                        "asat": now,
                        "asset_uri": None,
                    }
                )
        return [pd.DataFrame(rows)]


class FailingExtraction(ExtractionStrategy):
    def extract(self, task, storage):
        raise RuntimeError("extract boom")


class FailingTransform(TransformStrategy):
    def transform(self, task, batches):
        raise RuntimeError("transform boom")


class TestETLPipeline:
    def test_full_run(self, tmp_path: Path):
        db = SQLiteBackend(":memory:")
        db.init_db()
        storage = DiskStorage(str(tmp_path / "store"))

        pipeline = ETLPipeline(
            extraction=MockExtraction(),
            transform=MockTransform(),
            upload=UploadStrategy(),
            storage=storage,
            db=db,
        )
        count = pipeline.run(_make_task())
        assert count == 2

    def test_extract_failure(self, tmp_path: Path):
        db = SQLiteBackend(":memory:")
        db.init_db()
        storage = DiskStorage(str(tmp_path / "store"))

        pipeline = ETLPipeline(
            extraction=FailingExtraction(),
            transform=MockTransform(),
            upload=UploadStrategy(),
            storage=storage,
            db=db,
        )
        with pytest.raises(ExtractionFailedException):
            pipeline.run(_make_task())

    def test_transform_failure(self, tmp_path: Path):
        db = SQLiteBackend(":memory:")
        db.init_db()
        storage = DiskStorage(str(tmp_path / "store"))

        pipeline = ETLPipeline(
            extraction=MockExtraction(),
            transform=FailingTransform(),
            upload=UploadStrategy(),
            storage=storage,
            db=db,
        )
        with pytest.raises(TransformFailedException):
            pipeline.run(_make_task())


class _TestOrch(OrchestrationStrategy):
    MANIFEST_MAP = {
        "conversations.json": "conversations",
        "stories.json": "stories",
    }


class TestOrchestrationStrategy:
    def test_discover(self):
        orch = _TestOrch()
        files = [
            "archive-1/conversations.json",
            "archive-1/stories.json",
            "archive-1/other.json",
        ]
        result = orch.discover_tasks("archive-1", files)
        types = {r["interaction_type"] for r in result}
        assert types == {"conversations", "stories"}

    def test_discover_ignores_suffix_match(self):
        orch = _TestOrch()
        files = ["archive-1/shared_conversations.json"]
        result = orch.discover_tasks("archive-1", files)
        assert result == []

    def test_discover_empty(self):
        orch = _TestOrch()
        result = orch.discover_tasks("archive-1", [])
        assert result == []

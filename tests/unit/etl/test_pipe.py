from __future__ import annotations

import datetime
from collections.abc import Iterator

import pytest
from pydantic import BaseModel

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.models.etl_task import EtlTask
from context_use.storage.base import StorageBackend


class MockRecord(BaseModel):
    role: str
    content: str


MOCK_PAYLOAD_VERSION = "1.0.0"


class MockPipe(Pipe[MockRecord]):
    provider = "test"
    interaction_type = "test_conversations"
    archive_version = "v1"
    archive_path_pattern = "conversations.json"
    record_schema = MockRecord

    def extract_file(
        self, source_uri: str, storage: StorageBackend
    ) -> Iterator[MockRecord]:
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
    archive_path_pattern = "conversations.json"
    record_schema = MockRecord

    def extract_file(
        self, source_uri: str, storage: StorageBackend
    ) -> Iterator[MockRecord]:
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


class TestPipe:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):

            class IncompletePipe(Pipe[MockRecord]):
                provider = "test"
                interaction_type = "test"
                archive_version = "v1"
                archive_path_pattern = "data.json"
                record_schema = MockRecord

                # Missing extract and transform
                pass

            IncompletePipe()  # type: ignore[reportAbstractUsage]

    def test_run_yields_thread_rows(self):
        pipe = MockPipe()
        task = EtlTask(
            archive_id="fake",
            provider="test",
            interaction_type="test_conversations",
            source_uris=["conversations.json"],
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
            source_uris=["conversations.json"],
        )
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
            source_uris=["conversations.json"],
        )
        rows = list(pipe.run(task, storage=None))  # type: ignore[arg-type]

        assert pipe.extracted_count == 3
        assert pipe.transformed_count == 2
        assert len(rows) == 2

    def test_source_uri_property_returns_first(self):
        """Backward-compat ``source_uri`` property returns the first URI."""
        task = EtlTask(
            archive_id="a1",
            provider="test",
            interaction_type="test_conversations",
            source_uris=["first.json", "second.json"],
        )
        assert task.source_uri == "first.json"

    def test_source_uris_stored_on_domain_model(self):
        task = EtlTask(
            archive_id="a1",
            provider="test",
            interaction_type="test_conversations",
            source_uris=["a.json", "b.json"],
        )
        assert task.source_uris == ["a.json", "b.json"]

    def test_source_uris_empty_raises(self):
        with pytest.raises(ValueError, match="source_uris must not be empty"):
            EtlTask(
                archive_id="a1",
                provider="test",
                interaction_type="test_conversations",
                source_uris=[],
            )

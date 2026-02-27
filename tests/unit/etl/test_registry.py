from __future__ import annotations

import datetime
from collections.abc import Iterator

import pytest
from pydantic import BaseModel

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.models.etl_task import EtlTask
from context_use.providers.types import InteractionConfig, ProviderConfig
from context_use.storage.base import StorageBackend


class _FakeRecord(BaseModel):
    value: str


class FakePipeA(Pipe[_FakeRecord]):
    provider = "test"
    interaction_type = "test_alpha"
    archive_version = 1
    archive_path_pattern = "data.json"
    record_schema = _FakeRecord

    def extract_file(
        self, source_uri: str, storage: StorageBackend
    ) -> Iterator[_FakeRecord]:
        yield _FakeRecord(value="a")

    def transform(self, record: _FakeRecord, task: EtlTask) -> ThreadRow:
        return ThreadRow(
            unique_key=f"a:{record.value}",
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=record.value,
            payload={"v": record.value},
            version="1.0.0",
            asat=datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC),
        )


class FakePipeB(Pipe[_FakeRecord]):
    provider = "test"
    interaction_type = "test_beta"
    archive_version = 1
    archive_path_pattern = "nested/other.json"
    record_schema = _FakeRecord

    def extract_file(
        self, source_uri: str, storage: StorageBackend
    ) -> Iterator[_FakeRecord]:
        yield _FakeRecord(value="b")

    def transform(self, record: _FakeRecord, task: EtlTask) -> ThreadRow:
        return ThreadRow(
            unique_key=f"b:{record.value}",
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=record.value,
            payload={"v": record.value},
            version="1.0.0",
            asat=datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC),
        )


class FakePipeGlob(Pipe[_FakeRecord]):
    """Pipe with a wildcard ``archive_path_pattern`` for fan-out tests."""

    provider = "test"
    interaction_type = "test_glob"
    archive_version = 1
    archive_path_pattern = "inbox/*/message_1.json"
    record_schema = _FakeRecord

    def extract_file(
        self, source_uri: str, storage: StorageBackend
    ) -> Iterator[_FakeRecord]:
        yield _FakeRecord(value="g")

    def transform(self, record: _FakeRecord, task: EtlTask) -> ThreadRow:
        return ThreadRow(
            unique_key=f"g:{record.value}",
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=record.value,
            payload={"v": record.value},
            version="1.0.0",
            asat=datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC),
        )


@pytest.fixture()
def cfg() -> ProviderConfig:
    return ProviderConfig(
        interactions=[
            InteractionConfig(pipe=FakePipeA),
            InteractionConfig(pipe=FakePipeB),
        ]
    )


class TestDiscoverTasks:
    def test_discover_matching_files(self, cfg: ProviderConfig):
        tasks = cfg.discover_tasks(
            "a1", ["a1/data.json", "a1/nested/other.json", "a1/readme.txt"], "test"
        )
        assert len(tasks) == 2
        types = {t.interaction_type for t in tasks}
        assert types == {"test_alpha", "test_beta"}
        for t in tasks:
            assert isinstance(t, EtlTask)
            assert t.provider == "test"
            assert t.archive_id == "a1"

    def test_discover_partial_match(self, cfg: ProviderConfig):
        tasks = cfg.discover_tasks("a1", ["a1/data.json"], "test")
        assert len(tasks) == 1
        assert tasks[0].interaction_type == "test_alpha"
        assert tasks[0].source_uri == "a1/data.json"

    def test_discover_empty_when_no_match(self, cfg: ProviderConfig):
        tasks = cfg.discover_tasks("a1", ["a1/readme.txt"], "test")
        assert tasks == []

    def test_discover_ignores_suffix_match(self, cfg: ProviderConfig):
        """``shared_data.json`` should NOT match ``data.json``."""
        tasks = cfg.discover_tasks(
            "a1", ["a1/data.json", "a1/shared_data.json"], "test"
        )
        assert len(tasks) == 1
        assert tasks[0].source_uri == "a1/data.json"

    def test_glob_pattern_bundles_into_one_task(self):
        """Wildcard pattern bundles all matched files into one EtlTask."""
        cfg = ProviderConfig(interactions=[InteractionConfig(pipe=FakePipeGlob)])
        files = [
            "a1/inbox/alice/message_1.json",
            "a1/inbox/bob/message_1.json",
            "a1/inbox/carol/message_1.json",
        ]
        tasks = cfg.discover_tasks("a1", files, "test")

        assert len(tasks) == 1
        task = tasks[0]
        assert task.source_uris == sorted(files)
        assert task.interaction_type == "test_glob"
        assert task.provider == "test"
        assert task.archive_id == "a1"

    def test_glob_pattern_no_match(self):
        """Wildcard pattern yields no tasks when nothing matches."""
        cfg = ProviderConfig(interactions=[InteractionConfig(pipe=FakePipeGlob)])
        tasks = cfg.discover_tasks("a1", ["a1/inbox/readme.txt"], "test")
        assert tasks == []

    def test_glob_pattern_mixed_with_exact(self):
        """Exact-match and glob-match pipes coexist in one config."""
        cfg = ProviderConfig(
            interactions=[
                InteractionConfig(pipe=FakePipeA),
                InteractionConfig(pipe=FakePipeGlob),
            ]
        )
        files = [
            "a1/data.json",
            "a1/inbox/alice/message_1.json",
            "a1/inbox/bob/message_1.json",
        ]
        tasks = cfg.discover_tasks("a1", files, "test")

        assert len(tasks) == 2
        types = {t.interaction_type for t in tasks}
        assert types == {"test_alpha", "test_glob"}
        alpha_tasks = [t for t in tasks if t.interaction_type == "test_alpha"]
        glob_tasks = [t for t in tasks if t.interaction_type == "test_glob"]
        assert len(alpha_tasks) == 1
        assert alpha_tasks[0].source_uris == ["a1/data.json"]
        assert len(glob_tasks) == 1
        assert glob_tasks[0].source_uris == [
            "a1/inbox/alice/message_1.json",
            "a1/inbox/bob/message_1.json",
        ]

    def test_source_uri_property_returns_first(self, cfg: ProviderConfig):
        """Backward-compat ``source_uri`` property on discovered tasks."""
        tasks = cfg.discover_tasks("a1", ["a1/data.json"], "test")
        assert len(tasks) == 1
        assert tasks[0].source_uri == "a1/data.json"

    def test_source_uris_sorted(self):
        """Files within a bundled task are sorted for determinism."""
        cfg = ProviderConfig(interactions=[InteractionConfig(pipe=FakePipeGlob)])
        # Files deliberately out of order
        files = [
            "a1/inbox/carol/message_1.json",
            "a1/inbox/alice/message_1.json",
            "a1/inbox/bob/message_1.json",
        ]
        tasks = cfg.discover_tasks("a1", files, "test")
        assert len(tasks) == 1
        assert tasks[0].source_uris == [
            "a1/inbox/alice/message_1.json",
            "a1/inbox/bob/message_1.json",
            "a1/inbox/carol/message_1.json",
        ]


class TestGetPipe:
    def test_returns_correct_pipe(self, cfg: ProviderConfig):
        assert cfg.get_pipe("test_alpha") is FakePipeA
        assert cfg.get_pipe("test_beta") is FakePipeB

    def test_raises_for_unknown(self, cfg: ProviderConfig):
        with pytest.raises(KeyError, match="test_gamma"):
            cfg.get_pipe("test_gamma")

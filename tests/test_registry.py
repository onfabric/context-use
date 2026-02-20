from __future__ import annotations

import datetime
from collections.abc import Iterator

import pytest
from pydantic import BaseModel

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.models.etl_task import EtlTask
from context_use.etl.providers.registry import ProviderConfig
from context_use.storage.base import StorageBackend


class _FakeRecord(BaseModel):
    value: str


class FakePipeA(Pipe[_FakeRecord]):
    provider = "test"
    interaction_type = "test_alpha"
    archive_version = "v1"
    archive_path = "data.json"
    record_schema = _FakeRecord

    def extract(self, task: EtlTask, storage: StorageBackend) -> Iterator[_FakeRecord]:
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
    archive_version = "v1"
    archive_path = "nested/other.json"
    record_schema = _FakeRecord

    def extract(self, task: EtlTask, storage: StorageBackend) -> Iterator[_FakeRecord]:
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


@pytest.fixture()
def cfg() -> ProviderConfig:
    return ProviderConfig(pipes=[FakePipeA, FakePipeB])


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


class TestGetPipe:
    def test_returns_correct_pipe(self, cfg: ProviderConfig):
        assert cfg.get_pipe("test_alpha") is FakePipeA
        assert cfg.get_pipe("test_beta") is FakePipeB

    def test_raises_for_unknown(self, cfg: ProviderConfig):
        with pytest.raises(KeyError, match="test_gamma"):
            cfg.get_pipe("test_gamma")

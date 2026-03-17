from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import ClassVar

import pytest
from pydantic import BaseModel

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.core import make_thread_payload
from context_use.models.etl_task import EtlTask, EtlTaskStatus
from context_use.storage.base import StorageBackend
from context_use.storage.disk import DiskStorage


class ExtractConformanceTests:
    """Auto-generated conformance tests for the extract stage."""

    pipe_class: ClassVar[type[Pipe]]
    expected_extract_count: ClassVar[int]

    def test_extract_yields_record_schema_instances(
        self, extracted_records: list[BaseModel]
    ) -> None:
        assert len(extracted_records) >= 1, "extract() should yield at least one record"
        for r in extracted_records:
            assert isinstance(r, self.pipe_class.record_schema), (
                f"Expected {self.pipe_class.record_schema.__name__}, "
                f"got {type(r).__name__}"
            )

    def test_extract_count(self, extracted_records: list[BaseModel]) -> None:
        assert len(extracted_records) == self.expected_extract_count


class TransformConformanceTests:
    """Auto-generated conformance tests for the transform stage."""

    pipe_class: ClassVar[type[Pipe]]
    expected_transform_count: ClassVar[int]
    expected_fibre_kind: ClassVar[str | None]

    def test_run_yields_well_formed_thread_rows(
        self, transformed_rows: list[ThreadRow]
    ) -> None:
        assert len(transformed_rows) >= 1, "run() should yield at least one ThreadRow"

        for row in transformed_rows:
            assert isinstance(row, ThreadRow)
            assert row.unique_key, "unique_key must be set"

            assert row.provider == self.pipe_class.provider, (
                f"provider mismatch: {row.provider!r} != {self.pipe_class.provider!r}"
            )
            assert row.interaction_type == self.pipe_class.interaction_type, (
                f"interaction_type mismatch: "
                f"{row.interaction_type!r} "
                f"!= {self.pipe_class.interaction_type!r}"
            )

            assert row.version, "ThreadRow.version must be set"
            assert row.asat is not None, "ThreadRow.asat must be set"
            assert row.asat.tzinfo is not None, "ThreadRow.asat must be timezone-aware"
            assert row.asat <= datetime.now(UTC), (
                "ThreadRow.asat must not be in the future"
            )

            assert isinstance(row.payload, dict), "payload must be a dict"
            assert "fibreKind" in row.payload, "payload must contain 'fibreKind'"

            assert row.preview, "Preview should not be empty"

    def test_run_count(self, transformed_rows: list[ThreadRow]) -> None:
        assert len(transformed_rows) == self.expected_transform_count

    def test_unique_keys_are_unique(self, transformed_rows: list[ThreadRow]) -> None:
        keys = [r.unique_key for r in transformed_rows]
        assert len(keys) == len(set(keys)), (
            f"Duplicate unique_keys: {[k for k in keys if keys.count(k) > 1]}"
        )

    def test_fibre_kind(self, transformed_rows: list[ThreadRow]) -> None:
        if self.expected_fibre_kind is None:
            pytest.skip("expected_fibre_kind not set")
        for row in transformed_rows:
            assert row.payload["fibreKind"] == self.expected_fibre_kind

    def test_payload_round_trips(self, transformed_rows: list[ThreadRow]) -> None:
        for row in transformed_rows:
            parsed = make_thread_payload(row.payload)
            assert parsed is not None
            assert parsed.to_dict() == row.payload


class PipeTestKit(ExtractConformanceTests, TransformConformanceTests):
    """Full Pipe conformance suite covering both extract and transform stages.

    Subclass this and set:

    - ``pipe_class``: the :class:`Pipe` subclass under test
    - ``expected_extract_count``: expected number of extracted records
    - ``expected_transform_count``: expected number of transformed rows
    - ``fixture_data``: JSON-serialisable fixture data
    - ``fixture_key``: storage key (e.g. ``"archive/path/data.json"``)

    If ``fixture_data`` and ``fixture_key`` are set, ``pipe_fixture`` is
    auto-generated.  Otherwise, override the ``pipe_fixture`` fixture manually.

    Convenience fixtures ``extracted_records`` and ``transformed_rows``
    eliminate per-method boilerplate in provider-specific tests.
    """

    expected_extract_count: ClassVar[int]
    expected_transform_count: ClassVar[int]

    fixture_data: ClassVar[dict | list | None] = None
    fixture_key: ClassVar[str | None] = None

    expected_fibre_kind: ClassVar[str | None] = None

    expected_rows: ClassVar[list[dict] | None] = None

    @pytest.fixture()
    def pipe_fixture(self, tmp_path) -> tuple[StorageBackend, str]:
        if self.fixture_data is not None and self.fixture_key is not None:
            storage = DiskStorage(str(tmp_path / "store"))
            storage.write(
                self.fixture_key,
                json.dumps(self.fixture_data).encode(),
            )
            return storage, self.fixture_key
        raise NotImplementedError(
            "Subclasses must set fixture_data + fixture_key or override pipe_fixture"
        )

    @pytest.fixture()
    def extracted_records(self, pipe_fixture) -> list[BaseModel]:
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        return list(pipe.extract(task, storage))

    @pytest.fixture()
    def transformed_rows(self, pipe_fixture) -> list[ThreadRow]:
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        return list(pipe.run(task, storage))

    def _make_task(self, key: str) -> EtlTask:
        return EtlTask(
            archive_id="a1",
            provider=self.pipe_class.provider,
            interaction_type=self.pipe_class.interaction_type,
            source_uris=[key],
            status=EtlTaskStatus.CREATED.value,
        )

    def test_counts_tracked(self, pipe_fixture) -> None:
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        list(pipe.run(task, storage))
        assert pipe.extracted_count == self.expected_extract_count, (
            f"extracted_count {pipe.extracted_count} "
            f"!= expected {self.expected_extract_count}"
        )
        assert pipe.transformed_count == self.expected_transform_count, (
            f"transformed_count {pipe.transformed_count} "
            f"!= expected {self.expected_transform_count}"
        )
        assert pipe.error_count == 0, (
            f"error_count {pipe.error_count} != 0 — "
            "fixture data should not trigger errors"
        )

    def test_unique_keys_are_stable(self, pipe_fixture) -> None:
        storage, key = pipe_fixture
        task = self._make_task(key)
        first = [r.unique_key for r in self.pipe_class().run(task, storage)]
        second = [r.unique_key for r in self.pipe_class().run(task, storage)]
        assert first == second, "unique_keys must be deterministic across runs"

    def test_row_snapshots(self, transformed_rows: list[ThreadRow]) -> None:
        if self.expected_rows is None:
            pytest.skip("expected_rows not set")
        assert len(transformed_rows) == len(self.expected_rows), (
            f"row count {len(transformed_rows)} != expected {len(self.expected_rows)}"
        )
        for i, (row, expected) in enumerate(
            zip(transformed_rows, self.expected_rows, strict=True)
        ):
            label = f"row[{i}]"
            if "unique_key" in expected:
                assert row.unique_key == expected["unique_key"], (
                    f"{label} unique_key: "
                    f"{row.unique_key!r} != {expected['unique_key']!r}"
                )
            if "preview" in expected:
                assert row.preview == expected["preview"], (
                    f"{label} preview: {row.preview!r} != {expected['preview']!r}"
                )
            if "payload" in expected:
                assert row.payload == expected["payload"], f"{label} payload mismatch"
            if "asat" in expected:
                assert row.asat == expected["asat"], (
                    f"{label} asat: {row.asat} != {expected['asat']}"
                )

    def test_class_vars_set(self) -> None:
        cls = self.pipe_class
        assert cls.provider, "provider ClassVar must be set"
        assert cls.interaction_type, "interaction_type ClassVar must be set"
        assert isinstance(cls.archive_version, int), (
            "archive_version ClassVar must be set to an int"
        )
        assert cls.archive_path_pattern, "archive_path_pattern ClassVar must be set"
        assert cls.record_schema is not None, "record_schema ClassVar must be set"

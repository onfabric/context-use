from __future__ import annotations

from typing import ClassVar

import pytest

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.models.etl_task import EtlTask, EtlTaskStatus
from context_use.storage.base import StorageBackend


class PipeTestKit:
    """Base class for Pipe conformance tests.

    Subclass this and set:

    - ``pipe_class``: the :class:`Pipe` subclass under test
    - ``expected_extract_count``: expected number of extracted records
    - ``expected_transform_count``: expected number of transformed rows

    Then provide a ``pipe_fixture`` pytest fixture that returns
    ``(storage, key)`` where *storage* is a :class:`StorageBackend`
    with the fixture data written at *key*.

    Auto-generated tests
    --------------------
    - **Extract phase:** ``test_extract_yields_record_schema_instances``,
      ``test_extract_count``
    - **Transform phase (via ``run()``):**
      ``test_run_yields_well_formed_thread_rows``, ``test_run_count``,
      ``test_unique_keys_are_unique``
    - **Counts:** ``test_counts_tracked``
    - **Class vars:** ``test_class_vars_set``
    """

    pipe_class: ClassVar[type[Pipe]]
    expected_extract_count: ClassVar[int]
    expected_transform_count: ClassVar[int]

    @pytest.fixture()
    def pipe_fixture(self, tmp_path) -> tuple[StorageBackend, str]:
        """Return ``(storage, key)`` with fixture data loaded.

        Subclasses **must** override this fixture.
        """
        raise NotImplementedError(
            "Subclasses must implement pipe_fixture returning (StorageBackend, key)"
        )

    def _make_task(self, key: str) -> EtlTask:
        """Build a transient :class:`EtlTask` from pipe class vars."""
        return EtlTask(
            archive_id="a1",
            provider=self.pipe_class.provider,
            interaction_type=self.pipe_class.interaction_type,
            source_uri=key,
            status=EtlTaskStatus.CREATED.value,
        )

    def test_extract_yields_record_schema_instances(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        records = list(pipe.extract(task, storage))
        assert len(records) >= 1, "extract() should yield at least one record"
        for r in records:
            assert isinstance(r, self.pipe_class.record_schema), (
                f"Expected {self.pipe_class.record_schema.__name__}, "
                f"got {type(r).__name__}"
            )

    def test_extract_count(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        records = list(pipe.extract(task, storage))
        assert len(records) == self.expected_extract_count

    def test_run_yields_well_formed_thread_rows(self, pipe_fixture):
        """Single run() call that checks every ThreadRow field contract.

        Validates: isinstance, provider, interaction_type, version,
        asat, unique_key prefix, payload dict + fibre_kind, preview.
        """
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))

        assert len(rows) >= 1, "run() should yield at least one ThreadRow"

        prefix = f"{self.pipe_class.interaction_type}:"

        for row in rows:
            assert isinstance(row, ThreadRow)

            # unique_key starts with interaction_type:
            assert row.unique_key.startswith(prefix), (
                f"unique_key {row.unique_key!r} should start with {prefix!r}"
            )

            # provider and interaction_type propagated correctly
            assert row.provider == self.pipe_class.provider, (
                f"provider mismatch: {row.provider!r} != {self.pipe_class.provider!r}"
            )
            assert row.interaction_type == self.pipe_class.interaction_type, (
                f"interaction_type mismatch: {row.interaction_type!r} "
                f"!= {self.pipe_class.interaction_type!r}"
            )

            # version and asat populated
            assert row.version, "ThreadRow.version must be set"
            assert row.asat is not None, "ThreadRow.asat must be set"

            # payload is dict with fibre_kind
            assert isinstance(row.payload, dict), "payload must be a dict"
            assert "fibre_kind" in row.payload, "payload must contain 'fibre_kind'"

            # preview non-empty
            assert row.preview, "Preview should not be empty"

    def test_run_count(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        assert len(rows) == self.expected_transform_count

    def test_unique_keys_are_unique(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        keys = [r.unique_key for r in rows]
        assert len(keys) == len(set(keys)), (
            f"Duplicate unique_keys found: {[k for k in keys if keys.count(k) > 1]}"
        )

    def test_counts_tracked(self, pipe_fixture):
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

    def test_class_vars_set(self):
        cls = self.pipe_class
        assert cls.provider, "provider ClassVar must be set"
        assert cls.interaction_type, "interaction_type ClassVar must be set"
        assert cls.archive_version, "archive_version ClassVar must be set"
        assert cls.archive_path_pattern, "archive_path_pattern ClassVar must be set"
        assert cls.record_schema is not None, "record_schema ClassVar must be set"

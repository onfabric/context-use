from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.google.discover import GoogleDiscoverPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import GOOGLE_DISCOVER_JSON

_BASE = "Portability/My Activity"


def _write_fixture(tmp_path: Path, data: list[dict]) -> tuple[DiskStorage, str]:
    storage = DiskStorage(str(tmp_path / "store"))
    key = f"archive/{_BASE}/Discover/MyActivity.json"
    storage.write(key, json.dumps(data).encode())
    return storage, key


class TestGoogleDiscoverPipe(PipeTestKit):
    pipe_class = GoogleDiscoverPipe
    # 3 records in fixture: 1 feed summary ("cards in your feed") filtered out,
    # 2 "Visited Content From Discover" kept.
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        return _write_fixture(tmp_path, GOOGLE_DISCOVER_JSON)

    def test_feed_summary_filtered(self, pipe_fixture):
        """Feed summary records ('X cards in your feed') are dropped."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        records = list(pipe.extract(task, storage))
        titles = [r.title for r in records]
        assert not any("cards in your feed" in t for t in titles)

    def test_all_payloads_are_views(self, pipe_fixture):
        """All surviving Discover records should produce View fibres."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "View"

    def test_preview_text(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        previews = [r.preview for r in rows]
        assert all("Content From Discover" in p for p in previews)

from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.google.shopping import GoogleShoppingPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.google.conftest import GOOGLE_SHOPPING_JSON

_BASE = "Portability/My Activity"


def _write_fixture(tmp_path: Path, data: list[dict]) -> tuple[DiskStorage, str]:
    storage = DiskStorage(str(tmp_path / "store"))
    key = f"archive/{_BASE}/Shopping/MyActivity.json"
    storage.write(key, json.dumps(data).encode())
    return storage, key


class TestGoogleShoppingPipe(PipeTestKit):
    pipe_class = GoogleShoppingPipe
    # 4 records in fixture, 1 has unrecognised prefix → 3 extracted
    expected_extract_count = 3
    expected_transform_count = 3

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        return _write_fixture(tmp_path, GOOGLE_SHOPPING_JSON)

    def test_unrecognised_prefix_filtered(self, pipe_fixture):
        """Records with unknown prefixes ('Used') are dropped."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        records = list(pipe.extract(task, storage))
        titles = [r.title for r in records]
        assert not any(t.startswith("Used") for t in titles)

    def test_search_and_view_payloads(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        kinds = {r.payload["fibreKind"] for r in rows}
        assert "Search" in kinds
        assert "View" in kinds

    def test_shopping_urls_not_unwrapped(self, pipe_fixture):
        """Shopping URLs are not google.com/url redirects — kept as-is."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        for row in rows:
            url = row.payload["object"].get("url")
            if url:
                assert "google.com" in url

    def test_preview_text(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        previews = [r.preview for r in rows]
        assert any("headphones" in p.lower() for p in previews)

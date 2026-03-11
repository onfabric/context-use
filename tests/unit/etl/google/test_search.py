from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.google.search import (
    GoogleImageSearchPipe,
    GoogleSearchPipe,
    GoogleVideoSearchPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.google.conftest import (
    GOOGLE_IMAGE_SEARCH_JSON,
    GOOGLE_SEARCH_JSON,
    GOOGLE_VIDEO_SEARCH_JSON,
)

_BASE = "Portability/My Activity"


def _write_fixture(
    tmp_path: Path, subdir: str, data: list[dict]
) -> tuple[DiskStorage, str]:
    storage = DiskStorage(str(tmp_path / "store"))
    key = f"archive/{_BASE}/{subdir}/MyActivity.json"
    storage.write(key, json.dumps(data).encode())
    return storage, key


class TestGoogleSearchPipe(PipeTestKit):
    pipe_class = GoogleSearchPipe
    # 4 records in fixture, 1 has unrecognised prefix → 3 extracted, 3 transformed
    expected_extract_count = 3
    expected_transform_count = 3

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        return _write_fixture(tmp_path, "Search", GOOGLE_SEARCH_JSON)

    def test_unrecognised_prefix_filtered(self, pipe_fixture):
        """Records with unknown prefixes should be dropped in extract."""
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

    def test_redirect_url_unwrapped(self, pipe_fixture):
        """Google /url redirect URLs should be unwrapped to the actual URL."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        view_rows = [r for r in rows if r.payload["fibreKind"] == "View"]
        for row in view_rows:
            url = row.payload["object"].get("url")
            if url:
                assert "google.com/url" not in url

    def test_search_url_preserved(self, pipe_fixture):
        """Non-redirect Google URLs (google.com/search) should be kept as-is."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        search_rows = [r for r in rows if r.payload["fibreKind"] == "Search"]
        for row in search_rows:
            url = row.payload["object"].get("url")
            if url and "google.com/search" in url:
                assert url.startswith("https://www.google.com/search")

    def test_preview_text(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        previews = [r.preview for r in rows]
        assert any("python tutorials" in p for p in previews)


class TestGoogleVideoSearchPipe(PipeTestKit):
    pipe_class = GoogleVideoSearchPipe
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        return _write_fixture(tmp_path, "Video Search", GOOGLE_VIDEO_SEARCH_JSON)

    def test_payload_types(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        kinds = {r.payload["fibreKind"] for r in rows}
        assert "Search" in kinds
        assert "View" in kinds


class TestGoogleImageSearchPipe(PipeTestKit):
    pipe_class = GoogleImageSearchPipe
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        return _write_fixture(tmp_path, "Image Search", GOOGLE_IMAGE_SEARCH_JSON)

    def test_payload_types(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        kinds = {r.payload["fibreKind"] for r in rows}
        assert "Search" in kinds
        assert "View" in kinds

    def test_search_url_not_unwrapped(self, pipe_fixture):
        """google.com/search URLs should be preserved, not have q= extracted."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        search_rows = [r for r in rows if r.payload["fibreKind"] == "Search"]
        assert len(search_rows) >= 1
        url = search_rows[0].payload["object"].get("url")
        # URL should be the original google.com/search?q=...
        assert url is not None
        assert "google.com/search" in url

    def test_redirect_url_unwrapped(self, pipe_fixture):
        """google.com/url redirect URLs should be unwrapped."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        view_rows = [r for r in rows if r.payload["fibreKind"] == "View"]
        assert len(view_rows) >= 1
        url = view_rows[0].payload["object"].get("url")
        assert url is not None
        assert "example.com" in url
        assert "google.com/url" not in url

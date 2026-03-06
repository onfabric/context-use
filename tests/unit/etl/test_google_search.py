from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.google.search import (
    GoogleDiscoverPipe,
    GoogleImageSearchPipe,
    GoogleLensPipe,
    GoogleSearchPipe,
    GoogleVideoSearchPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import (
    GOOGLE_DISCOVER_JSON,
    GOOGLE_IMAGE_SEARCH_JSON,
    GOOGLE_LENS_JSON,
    GOOGLE_SEARCH_JSON,
    GOOGLE_VIDEO_SEARCH_JSON,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE = "Portability/My Activity"


def _write_fixture(
    tmp_path: Path, subdir: str, data: list[dict]
) -> tuple[DiskStorage, str]:
    storage = DiskStorage(str(tmp_path / "store"))
    key = f"archive/{_BASE}/{subdir}/MyActivity.json"
    storage.write(key, json.dumps(data).encode())
    return storage, key


# ---------------------------------------------------------------------------
# Google Search
# ---------------------------------------------------------------------------


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

    def test_url_unwrapped(self, pipe_fixture):
        """Google redirect URLs should be unwrapped to the actual URL."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        search_rows = [r for r in rows if r.payload["fibreKind"] == "Search"]
        for row in search_rows:
            url = row.payload["object"].get("url")
            if url:
                assert "google.com/url" not in url

    def test_preview_text(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        previews = [r.preview for r in rows]
        assert any("python tutorials" in p for p in previews)


# ---------------------------------------------------------------------------
# Google Video Search
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Google Image Search
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Google Lens
# ---------------------------------------------------------------------------


class TestGoogleLensPipe(PipeTestKit):
    pipe_class = GoogleLensPipe
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        return _write_fixture(tmp_path, "Google Lens", GOOGLE_LENS_JSON)

    def test_all_search_fibres(self, pipe_fixture):
        """Lens records always produce FibreSearch."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "Search"

    def test_page_object_type(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["object"]["type"] == "Page"


# ---------------------------------------------------------------------------
# Google Discover
# ---------------------------------------------------------------------------


class TestGoogleDiscoverPipe(PipeTestKit):
    pipe_class = GoogleDiscoverPipe
    # 3 records in fixture, 1 has unrecognised prefix → 2 extracted, 2 transformed
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        return _write_fixture(tmp_path, "Discover", GOOGLE_DISCOVER_JSON)

    def test_all_view_fibres(self, pipe_fixture):
        """Discover records with 'Viewed' prefix produce FibreViewObject."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "View"

    def test_preview_uses_via_google(self, pipe_fixture):
        """Google provider previews should use 'via google' not 'on google'."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        for row in rows:
            assert "via google" in row.preview

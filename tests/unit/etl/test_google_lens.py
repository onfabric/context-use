
import json
from pathlib import Path

import pytest

from context_use.providers.google.lens import GoogleLensPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import GOOGLE_LENS_JSON

_BASE = "Portability/My Activity"


def _write_fixture(tmp_path: Path, data: list[dict]) -> tuple[DiskStorage, str]:
    storage = DiskStorage(str(tmp_path / "store"))
    key = f"archive/{_BASE}/Google Lens/MyActivity.json"
    storage.write(key, json.dumps(data).encode())
    return storage, key


class TestGoogleLensPipe(PipeTestKit):
    pipe_class = GoogleLensPipe
    # 4 records in fixture: 2 bare "Searched with Google Lens" filtered out,
    # 1 "Searched for ..." + 1 "Searched with Google Lens + ..." kept.
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        return _write_fixture(tmp_path, GOOGLE_LENS_JSON)

    def test_bare_lens_search_filtered(self, pipe_fixture):
        """Bare 'Searched with Google Lens' records (no query) are dropped."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        records = list(pipe.extract(task, storage))
        for r in records:
            assert r.title != "Searched with Google Lens"

    def test_all_payloads_are_searches(self, pipe_fixture):
        """All surviving Lens records should produce Search fibres."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "Search"

    def test_lens_plus_query_extracted(self, pipe_fixture):
        """'Searched with Google Lens + "query"' extracts the quoted query."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        names = [row.payload["object"].get("name") for row in rows]
        assert "types of succulent plants" in names

    def test_searched_for_url_preserved(self, pipe_fixture):
        """'Searched for ...' records keep the google.com/search URL."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        urls = [row.payload["object"].get("url") for row in rows]
        assert any(u and "google.com/search" in u for u in urls)

    def test_preview_text(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        previews = [r.preview for r in rows]
        assert any("succulent plants" in p for p in previews)

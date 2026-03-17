from __future__ import annotations

import pytest

from context_use.providers.netflix.search_history.pipe import (
    NetflixSearchHistoryPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.netflix.conftest import SEARCH_HISTORY_CSV


class TestNetflixSearchHistoryPipe(PipeTestKit):
    pipe_class = NetflixSearchHistoryPipe
    expected_extract_count = 2
    expected_transform_count = 2
    expected_fibre_kind = "Search"

    @pytest.fixture()
    def pipe_fixture(self, tmp_path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/CONTENT_INTERACTION/SearchHistory.csv"
        storage.write(key, SEARCH_HISTORY_CSV)
        return storage, key

    def test_query_typed_preferred_over_displayed_name(self, transformed_rows):
        row_with_query = transformed_rows[0]
        assert '"comedy"' in row_with_query.preview

    def test_displayed_name_fallback(self, transformed_rows):
        row_without_query = transformed_rows[1]
        assert "The Great Adventure" in row_without_query.preview

    def test_preview_format(self, transformed_rows):
        for row in transformed_rows:
            assert row.preview.startswith("Searched")
            assert "Netflix" in row.preview

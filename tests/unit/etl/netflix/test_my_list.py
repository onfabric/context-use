from __future__ import annotations

import pytest

from context_use.providers.netflix.my_list.pipe import NetflixMyListPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.netflix.conftest import MY_LIST_CSV


class TestNetflixMyListPipe(PipeTestKit):
    pipe_class = NetflixMyListPipe
    expected_extract_count = 2
    expected_transform_count = 2
    expected_fibre_kind = "AddToCollection"

    @pytest.fixture()
    def pipe_fixture(self, tmp_path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/CONTENT_INTERACTION/MyList.csv"
        storage.write(key, MY_LIST_CSV)
        return storage, key

    def test_collection_name_is_my_list(self, transformed_rows):
        for row in transformed_rows:
            assert row.payload["target"]["name"] == "My List"

    def test_preview_format(self, transformed_rows):
        for row in transformed_rows:
            assert "My List" in row.preview
            assert "Netflix" in row.preview

    def test_date_only_parsing(self, transformed_rows):
        for row in transformed_rows:
            assert row.asat.hour == 0
            assert row.asat.minute == 0

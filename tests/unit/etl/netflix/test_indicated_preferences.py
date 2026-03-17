from __future__ import annotations

import pytest

from context_use.providers.netflix.indicated_preferences.pipe import (
    NetflixIndicatedPreferencesPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.netflix.conftest import INDICATED_PREFERENCES_CSV


class TestNetflixIndicatedPreferencesPipe(PipeTestKit):
    pipe_class = NetflixIndicatedPreferencesPipe
    expected_extract_count = 2
    expected_transform_count = 2
    expected_fibre_kind = "Reaction"

    @pytest.fixture()
    def pipe_fixture(self, tmp_path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/CONTENT_INTERACTION/IndicatedPreferences.csv"
        storage.write(key, INDICATED_PREFERENCES_CSV)
        return storage, key

    def test_interested_false_becomes_dislike(self, transformed_rows):
        dislike_rows = [r for r in transformed_rows if r.payload["type"] == "Dislike"]
        assert len(dislike_rows) == 1
        assert "The Great Adventure" in dislike_rows[0].preview

    def test_interested_true_becomes_like(self, transformed_rows):
        like_rows = [r for r in transformed_rows if r.payload["type"] == "Like"]
        assert len(like_rows) == 1
        assert "Comedy Hour" in like_rows[0].preview

    def test_payload_object_is_video(self, transformed_rows):
        for row in transformed_rows:
            assert row.payload["object"]["type"] == "Video"

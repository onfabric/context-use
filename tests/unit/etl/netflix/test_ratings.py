from __future__ import annotations

import pytest

from context_use.providers.netflix.ratings.pipe import NetflixRatingsPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.netflix.conftest import RATINGS_CSV


class TestNetflixRatingsPipe(PipeTestKit):
    pipe_class = NetflixRatingsPipe
    expected_extract_count = 2
    expected_transform_count = 2
    expected_fibre_kind = "Reaction"

    @pytest.fixture()
    def pipe_fixture(self, tmp_path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/CONTENT_INTERACTION/Ratings.csv"
        storage.write(key, RATINGS_CSV)
        return storage, key

    def test_thumbs_zero_filtered(self, extracted_records):
        for record in extracted_records:
            assert record.thumbs_value != "0"

    def test_like_and_dislike_types(self, transformed_rows):
        types = {r.payload["type"] for r in transformed_rows}
        assert "Like" in types
        assert "Dislike" in types

    def test_preview_contains_title(self, transformed_rows):
        previews = [r.preview for r in transformed_rows]
        assert any("The Great Adventure" in p for p in previews)
        assert any("Bad Movie" in p for p in previews)

    def test_like_preview_format(self, transformed_rows):
        like_rows = [r for r in transformed_rows if r.payload["type"] == "Like"]
        assert len(like_rows) == 1
        assert like_rows[0].preview.startswith("Liked")

    def test_dislike_preview_format(self, transformed_rows):
        dislike_rows = [r for r in transformed_rows if r.payload["type"] == "Dislike"]
        assert len(dislike_rows) == 1
        assert dislike_rows[0].preview.startswith("Disliked")

from __future__ import annotations

import pytest

from context_use.providers.netflix.viewing_activity.pipe import (
    NetflixViewingActivityPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.netflix.conftest import VIEWING_ACTIVITY_CSV


class TestNetflixViewingActivityPipe(PipeTestKit):
    pipe_class = NetflixViewingActivityPipe
    expected_extract_count = 2
    expected_transform_count = 2
    expected_fibre_kind = "View"

    @pytest.fixture()
    def pipe_fixture(self, tmp_path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/CONTENT_INTERACTION/ViewingActivity.csv"
        storage.write(key, VIEWING_ACTIVITY_CSV)
        return storage, key

    def test_supplemental_video_filtered(self, extracted_records):
        for record in extracted_records:
            assert "hook" not in (record.source or "")

    def test_preview_contains_title(self, transformed_rows):
        previews = [r.preview for r in transformed_rows]
        assert any("The Great Adventure" in p for p in previews)
        assert any("Comedy Hour" in p for p in previews)

    def test_payload_object_is_video(self, transformed_rows):
        for row in transformed_rows:
            assert row.payload["object"]["type"] == "Video"

    def test_preview_contains_provider(self, transformed_rows):
        for row in transformed_rows:
            assert "Netflix" in row.preview

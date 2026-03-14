from __future__ import annotations

from pathlib import Path

from context_use.providers.instagram.videos_watched.pipe import (
    InstagramVideosWatchedPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit, VideoObjectMixin
from tests.unit.etl.instagram.conftest import (
    INSTAGRAM_VIDEOS_WATCHED_V1_JSON,
)


class TestInstagramVideosWatchedV1Pipe(VideoObjectMixin, PipeTestKit):
    pipe_class = InstagramVideosWatchedPipe
    expected_extract_count = 1
    expected_transform_count = 1
    fixture_data = INSTAGRAM_VIDEOS_WATCHED_V1_JSON
    fixture_key = "archive/ads_information/ads_and_topics/videos_watched.json"
    expected_fibre_kind = "View"

    def test_non_array_produces_no_rows(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        assert self.fixture_key is not None
        key = self.fixture_key
        storage.write(key, b'{"not": "an array"}')
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 0

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.author is None
        assert record.video_url == "https://www.instagram.com/reel/SYNTHETIC_VIDEO/"
        assert record.timestamp == 1770746034
        assert record.source is not None

    def test_payload_object_url(self, transformed_rows):
        obj = transformed_rows[0].payload["object"]
        assert obj["url"] == "https://www.instagram.com/reel/SYNTHETIC_VIDEO/"
        assert "attributedTo" not in obj

    def test_preview_includes_url(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Viewed video" in preview
        assert "SYNTHETIC_VIDEO" in preview

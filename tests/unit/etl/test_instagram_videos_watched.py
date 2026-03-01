from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.instagram.videos_watched import (
    InstagramVideosWatchedPipe,
    InstagramVideosWatchedV0Pipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import (
    INSTAGRAM_VIDEOS_WATCHED_V0_JSON,
    INSTAGRAM_VIDEOS_WATCHED_V1_JSON,
)

ARCHIVE_PATH = "ads_information/ads_and_topics/videos_watched.json"


# ---------------------------------------------------------------------------
# V0 tests
# ---------------------------------------------------------------------------


class TestInstagramVideosWatchedV0Pipe(PipeTestKit):
    pipe_class = InstagramVideosWatchedV0Pipe
    expected_extract_count = 3
    expected_transform_count = 3

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_VIDEOS_WATCHED_V0_JSON).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.author == "synthetic_creator_1"
        assert record.timestamp == 1743840091
        assert record.source is not None

    def test_payload_is_view(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "View"
            assert row.payload["type"] == "View"

    def test_payload_object_is_video(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            obj = row.payload["object"]
            assert obj["type"] == "Video"

    def test_payload_has_attributed_to_profile(self, pipe_fixture):
        """V0 data has an author → attributedTo should be a Profile."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        row = rows[0]
        attr = row.payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "synthetic_creator_1"
        assert attr["url"] == "https://www.instagram.com/synthetic_creator_1"

    def test_preview_includes_author(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        preview = rows[0].preview
        assert "Viewed video" in preview
        assert "synthetic_creator_1" in preview
        assert "instagram" in preview.lower()

    def test_asat_from_timestamp(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        # First record has timestamp 1743840091
        assert rows[0].asat.year >= 2025

    def test_interaction_type(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.interaction_type == "instagram_videos_watched"


# ---------------------------------------------------------------------------
# V1 tests
# ---------------------------------------------------------------------------


class TestInstagramVideosWatchedV1Pipe(PipeTestKit):
    pipe_class = InstagramVideosWatchedPipe
    expected_extract_count = 1
    expected_transform_count = 1

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_VIDEOS_WATCHED_V1_JSON).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.author is None  # v1 has no author
        assert record.video_url == "https://www.instagram.com/reel/SYNTHETIC_VIDEO/"
        assert record.timestamp == 1770746034
        assert record.source is not None

    def test_payload_is_view(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "View"
            assert row.payload["type"] == "View"

    def test_payload_object_is_video_with_url(self, pipe_fixture):
        """V1 data has a URL → video object should carry url, no attributedTo."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        obj = rows[0].payload["object"]
        assert obj["type"] == "Video"
        assert obj["url"] == "https://www.instagram.com/reel/SYNTHETIC_VIDEO/"
        assert "attributedTo" not in obj

    def test_preview_includes_url(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        preview = rows[0].preview
        assert "Viewed video" in preview
        assert "SYNTHETIC_VIDEO" in preview

    def test_interaction_type(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.interaction_type == "instagram_videos_watched"

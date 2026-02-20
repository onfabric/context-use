from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.etl.providers.instagram.media import (
    InstagramReelsPipe,
    InstagramStoriesPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import INSTAGRAM_REELS_JSON, INSTAGRAM_STORIES_JSON


class TestInstagramStoriesPipe(PipeTestKit):
    pipe_class = InstagramStoriesPipe
    expected_extract_count = 3
    expected_transform_count = 3

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/your_instagram_activity/media/stories.json"
        storage.write(key, json.dumps(INSTAGRAM_STORIES_JSON).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.uri
        assert record.creation_timestamp > 0
        assert record.media_type in ("Image", "Video")
        assert record.source is not None

    def test_media_type_inference(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        types = [r.media_type for r in records]
        assert "Video" in types  # .mp4 file
        assert "Image" in types  # .jpg files

    def test_payload_is_create(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibre_kind"] == "Create"

    def test_asset_uri_populated(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.asset_uri is not None
            assert row.asset_uri.startswith(f"{task.archive_id}/")
            assert "media/stories/" in row.asset_uri


class TestInstagramReelsPipe(PipeTestKit):
    pipe_class = InstagramReelsPipe
    expected_extract_count = 1
    expected_transform_count = 1

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/your_instagram_activity/media/reels.json"
        storage.write(key, json.dumps(INSTAGRAM_REELS_JSON).encode())
        return storage, key

    def test_reel_is_video(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        assert records[0].media_type == "Video"

    def test_reel_transform(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 1
        assert rows[0].payload["fibre_kind"] == "Create"
        # Reel is video
        assert rows[0].payload["object"]["@type"] == "Video"

    def test_reel_asset_uri(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert rows[0].asset_uri is not None
        assert rows[0].asset_uri.startswith(f"{task.archive_id}/")
        assert "media/reels/" in rows[0].asset_uri

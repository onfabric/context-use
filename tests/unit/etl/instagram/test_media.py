from __future__ import annotations

from pathlib import Path

from context_use.providers.instagram.media import (
    InstagramPostsPipe,
    InstagramReelsPipe,
    InstagramStoriesPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.instagram.conftest import (
    INSTAGRAM_POSTS_JSON,
    INSTAGRAM_REELS_JSON,
    INSTAGRAM_STORIES_JSON,
)


class TestInstagramStoriesPipe(PipeTestKit):
    pipe_class = InstagramStoriesPipe
    expected_extract_count = 3
    expected_transform_count = 3
    expected_fibre_kind = "Create"
    fixture_data = INSTAGRAM_STORIES_JSON
    fixture_key = "archive/your_instagram_activity/media/stories.json"

    def test_file_schema_gates_missing_key(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        assert self.fixture_key is not None
        key = self.fixture_key
        storage.write(key, b'{"wrong_key": []}')
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 0
        assert pipe.error_count == 1

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.uri
        assert record.creation_timestamp > 0
        assert record.source is not None

    def test_media_type_in_payload(self, transformed_rows):
        types = [r.payload["object"]["type"] for r in transformed_rows]
        assert "Video" in types
        assert "Image" in types

    def test_asset_uri_populated(self, pipe_fixture, transformed_rows):
        _, key = pipe_fixture
        task = self._make_task(key)
        for row in transformed_rows:
            assert row.asset_uri is not None
            assert row.asset_uri.startswith(f"{task.archive_id}/")
            assert "media/stories/" in row.asset_uri


class TestInstagramReelsPipe(PipeTestKit):
    pipe_class = InstagramReelsPipe
    expected_extract_count = 1
    expected_transform_count = 1
    expected_fibre_kind = "Create"
    fixture_data = INSTAGRAM_REELS_JSON
    fixture_key = "archive/your_instagram_activity/media/reels.json"

    def test_file_schema_gates_missing_key(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        assert self.fixture_key is not None
        key = self.fixture_key
        storage.write(key, b'{"wrong_key": []}')
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 0
        assert pipe.error_count == 1

    def test_reel_transform(self, transformed_rows):
        assert len(transformed_rows) == 1
        assert transformed_rows[0].payload["object"]["type"] == "Video"

    def test_reel_asset_uri(self, pipe_fixture, transformed_rows):
        _, key = pipe_fixture
        task = self._make_task(key)
        row = transformed_rows[0]
        assert row.asset_uri is not None
        assert row.asset_uri.startswith(f"{task.archive_id}/")
        assert "media/reels/" in row.asset_uri


class TestInstagramPostsPipe(PipeTestKit):
    pipe_class = InstagramPostsPipe
    expected_extract_count = 1
    expected_transform_count = 1
    expected_fibre_kind = "Create"
    fixture_data = INSTAGRAM_POSTS_JSON
    fixture_key = "archive/your_instagram_activity/media/posts_1.json"

    def test_non_array_produces_no_rows(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        assert self.fixture_key is not None
        key = self.fixture_key
        storage.write(key, b'{"not": "an array"}')
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 0

    def test_post_title(self, extracted_records):
        assert extracted_records[0].title == "Homemade pasta for dinner"

    def test_post_transform(self, transformed_rows):
        assert len(transformed_rows) == 1
        assert transformed_rows[0].payload["object"]["type"] == "Image"

    def test_post_asset_uri(self, pipe_fixture, transformed_rows):
        _, key = pipe_fixture
        task = self._make_task(key)
        row = transformed_rows[0]
        assert row.asset_uri is not None
        assert row.asset_uri.startswith(f"{task.archive_id}/")
        assert "media/posts/" in row.asset_uri

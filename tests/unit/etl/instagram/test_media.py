from __future__ import annotations

from context_use.providers.instagram.media import (
    InstagramPostsPipe,
    InstagramReelsPipe,
    InstagramStoriesPipe,
)
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

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.uri
        assert record.creation_timestamp > 0
        assert record.media_type in ("Image", "Video")
        assert record.source is not None

    def test_media_type_inference(self, extracted_records):
        types = [r.media_type for r in extracted_records]
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

    def test_reel_is_video(self, extracted_records):
        assert extracted_records[0].media_type == "Video"

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

    def test_post_is_image(self, extracted_records):
        assert extracted_records[0].media_type == "Image"

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

from __future__ import annotations

from datetime import UTC, datetime

from context_use.providers.instagram.media.pipe import (
    InstagramPostsPipe,
    InstagramReelsPipe,
    InstagramStoriesPipe,
)
from context_use.storage.memory import InMemoryStorage
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
    snapshot_cases = [
        (
            {
                "ig_stories": [
                    {
                        "uri": "media/stories/202512/beach_waves.mp4",
                        "creation_timestamp": 1765390423,
                        "media_metadata": {
                            "video_metadata": {
                                "exif_data": [
                                    {
                                        "device_id": "android-0000000000000000",
                                        "camera_position": "unknown",
                                        "date_time_original": "20251210T181138.000Z",
                                        "source_type": "4",
                                    }
                                ]
                            },
                            "camera_metadata": {"has_camera_metadata": True},
                        },
                        "title": "",
                        "cross_post_source": {"source_app": "FB"},
                        "dubbing_info": [],
                        "media_variants": [],
                    }
                ]
            },
            {
                "preview": "Posted video on instagram",
                "asat": datetime(2025, 12, 10, 18, 13, 43, tzinfo=UTC),
                "payload": {
                    "fibreKind": "Create",
                    "type": "Create",
                    "published": "2025-12-10T18:13:43Z",
                    "object": {
                        "published": "2025-12-10T18:13:43Z",
                        "type": "Video",
                    },
                },
            },
        ),
    ]

    def test_file_schema_gates_missing_key(self):
        storage = InMemoryStorage()
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
            assert task.archive_id in row.asset_uri
            assert "media/stories/" in row.asset_uri


class TestInstagramReelsPipe(PipeTestKit):
    pipe_class = InstagramReelsPipe
    expected_extract_count = 1
    expected_transform_count = 1
    expected_fibre_kind = "Create"
    fixture_data = INSTAGRAM_REELS_JSON
    fixture_key = "archive/your_instagram_activity/media/reels.json"
    snapshot_cases = [
        (
            {
                "ig_reels_media": [
                    {
                        "media": [
                            {
                                "uri": "media/reels/202506/guitar_strum.mp4",
                                "creation_timestamp": 1750896174,
                                "media_metadata": {
                                    "video_metadata": {
                                        "subtitles": {
                                            "uri": (
                                                "media/reels/202506/guitar_strum.srt"
                                            ),
                                            "creation_timestamp": 1750896174,
                                        },
                                        "exif_data": [
                                            {
                                                "latitude": 51.5074,
                                                "longitude": -0.1278,
                                            },
                                            {
                                                "device_id": "android-0000000000000000",
                                                "camera_position": "unknown",
                                                "source_type": "4",
                                            },
                                        ],
                                    },
                                    "camera_metadata": {"has_camera_metadata": False},
                                },
                                "title": (
                                    "Synthetic reel about playing guitar at an open mic"
                                ),
                                "cross_post_source": {"source_app": "FB"},
                                "dubbing_info": [],
                                "media_variants": [],
                            }
                        ]
                    }
                ]
            },
            {
                "preview": "Posted video on instagram",
                "asat": datetime(2025, 6, 26, 0, 2, 54, tzinfo=UTC),
                "payload": {
                    "fibreKind": "Create",
                    "type": "Create",
                    "published": "2025-06-26T00:02:54Z",
                    "object": {
                        "name": ("Synthetic reel about playing guitar at an open mic"),
                        "published": "2025-06-26T00:02:54Z",
                        "type": "Video",
                    },
                },
            },
        ),
    ]

    def test_file_schema_gates_missing_key(self):
        storage = InMemoryStorage()
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
        assert task.archive_id in row.asset_uri
        assert "media/reels/" in row.asset_uri


class TestInstagramPostsPipe(PipeTestKit):
    pipe_class = InstagramPostsPipe
    expected_extract_count = 1
    expected_transform_count = 1
    expected_fibre_kind = "Create"
    fixture_data = INSTAGRAM_POSTS_JSON
    fixture_key = "archive/your_instagram_activity/media/posts_1.json"
    snapshot_cases = [
        (
            [
                {
                    "media": [
                        {
                            "uri": "media/posts/202409/pasta_flatlay.jpg",
                            "creation_timestamp": 1725373798,
                            "media_metadata": {
                                "photo_metadata": {
                                    "exif_data": [
                                        {"latitude": 48.8566, "longitude": 2.3522},
                                        {
                                            "scene_capture_type": "standard",
                                            "software": "HDR+ 1.0.000000000zd",
                                            "device_id": "android-0000000000000000",
                                            "date_time_digitized": (
                                                "2024:09:03 14:23:18"
                                            ),
                                            "date_time_original": (
                                                "2024:09:03 14:23:18"
                                            ),
                                            "source_type": "4",
                                        },
                                    ]
                                },
                                "camera_metadata": {"has_camera_metadata": False},
                            },
                            "title": "Homemade pasta for dinner",
                            "cross_post_source": {"source_app": "FB"},
                        }
                    ]
                }
            ],
            {
                "preview": "Posted image on instagram",
                "asat": datetime(2024, 9, 3, 14, 29, 58, tzinfo=UTC),
                "payload": {
                    "fibreKind": "Create",
                    "type": "Create",
                    "published": "2024-09-03T14:29:58Z",
                    "object": {
                        "name": "Homemade pasta for dinner",
                        "published": "2024-09-03T14:29:58Z",
                        "type": "Image",
                    },
                },
            },
        ),
    ]

    def test_non_array_produces_no_rows(self):
        storage = InMemoryStorage()
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
        assert task.archive_id in row.asset_uri
        assert "media/posts/" in row.asset_uri

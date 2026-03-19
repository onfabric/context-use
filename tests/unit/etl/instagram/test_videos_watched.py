from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from context_use.providers.instagram.videos_watched.pipe import (
    InstagramVideosWatchedPipe,
    InstagramVideosWatchedV0Pipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import AttributedToProfileMixin, PipeTestKit, VideoObjectMixin
from tests.unit.etl.instagram.conftest import (
    INSTAGRAM_VIDEOS_WATCHED_V0_JSON,
    INSTAGRAM_VIDEOS_WATCHED_V1_JSON,
)


class TestInstagramVideosWatchedV0Pipe(
    VideoObjectMixin, AttributedToProfileMixin, PipeTestKit
):
    pipe_class = InstagramVideosWatchedV0Pipe
    expected_extract_count = 3
    expected_transform_count = 3
    fixture_data = INSTAGRAM_VIDEOS_WATCHED_V0_JSON
    fixture_key = "archive/ads_information/ads_and_topics/videos_watched.json"
    expected_fibre_kind = "View"
    snapshot_cases = [
        (
            {
                "impressions_history_videos_watched": [
                    {
                        "string_map_data": {
                            "Author": {"value": "synthetic_creator_1"},
                            "Time": {"timestamp": 1743840091},
                        }
                    }
                ]
            },
            {
                "unique_key": "5ea43b56fd10556e",
                "preview": "Viewed video by synthetic_creator_1 on instagram",
                "asat": datetime(2025, 4, 5, 8, 1, 31, tzinfo=UTC),
                "payload": {
                    "type": "View",
                    "published": "2025-04-05T08:01:31Z",
                    "object": {
                        "type": "Video",
                        "attributedTo": {
                            "type": "Profile",
                            "name": "synthetic_creator_1",
                            "url": "https://www.instagram.com/synthetic_creator_1",
                        },
                    },
                    "fibreKind": "View",
                },
            },
        ),
        (
            {
                "impressions_history_videos_watched": [
                    {
                        "string_map_data": {
                            "Author": {"value": "synthetic_creator_2"},
                            "Time": {"timestamp": 1743840379},
                        }
                    }
                ]
            },
            {
                "unique_key": "15843430d05b1f87",
                "preview": "Viewed video by synthetic_creator_2 on instagram",
                "asat": datetime(2025, 4, 5, 8, 6, 19, tzinfo=UTC),
                "payload": {
                    "type": "View",
                    "published": "2025-04-05T08:06:19Z",
                    "object": {
                        "type": "Video",
                        "attributedTo": {
                            "type": "Profile",
                            "name": "synthetic_creator_2",
                            "url": "https://www.instagram.com/synthetic_creator_2",
                        },
                    },
                    "fibreKind": "View",
                },
            },
        ),
    ]

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
        assert record.author == "synthetic_creator_1"
        assert record.timestamp == 1743840091
        assert record.source is not None

    def test_attribution_name_and_url(self, transformed_rows):
        attr = transformed_rows[0].payload["object"]["attributedTo"]
        assert attr["name"] == "synthetic_creator_1"
        assert attr["url"] == "https://www.instagram.com/synthetic_creator_1"

    def test_preview_includes_author(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Viewed video" in preview
        assert "synthetic_creator_1" in preview
        assert "instagram" in preview.lower()


class TestInstagramVideosWatchedV1Pipe(VideoObjectMixin, PipeTestKit):
    pipe_class = InstagramVideosWatchedPipe
    expected_extract_count = 2
    expected_transform_count = 2
    fixture_data = INSTAGRAM_VIDEOS_WATCHED_V1_JSON
    fixture_key = "archive/ads_information/ads_and_topics/videos_watched.json"
    expected_fibre_kind = "View"
    snapshot_cases = [
        (
            [
                {
                    "timestamp": 1770746034,
                    "media": [],
                    "label_values": [
                        {
                            "label": "URL",
                            "value": "https://www.instagram.com/reel/SYNTHETIC_VIDEO/",
                            "href": "https://www.instagram.com/reel/SYNTHETIC_VIDEO/",
                        },
                    ],
                }
            ],
            {
                "unique_key": "6b78d036960432cb",
                "preview": "Viewed video"
                " https://www.instagram.com/reel/SYNTHETIC_VIDEO/"
                " on instagram",
                "asat": datetime(2026, 2, 10, 17, 53, 54, tzinfo=UTC),
                "payload": {
                    "type": "View",
                    "published": "2026-02-10T17:53:54Z",
                    "object": {
                        "type": "Video",
                        "url": "https://www.instagram.com/reel/SYNTHETIC_VIDEO/",
                    },
                    "fibreKind": "View",
                },
            },
        ),
        (
            [
                {
                    "timestamp": 1773153225,
                    "media": [],
                    "label_values": [
                        {
                            "label": "URL",
                            "value": "https://www.instagram.com/reel/SYNTHETIC_REEL_1/",
                            "href": "https://www.instagram.com/reel/SYNTHETIC_REEL_1/",
                        },
                        {
                            "dict": [
                                {
                                    "dict": [
                                        {
                                            "label": "URL",
                                            "value": "https://example.com/synthetic_creator_1",
                                        },
                                        {
                                            "label": "Name",
                                            "value": "Synthetic Creator 1",
                                        },
                                        {
                                            "label": "Username",
                                            "value": "synthetic_creator_1",
                                        },
                                    ],
                                    "title": "",
                                }
                            ],
                            "title": "Owner",
                        },
                    ],
                }
            ],
            {
                "unique_key": "17ee74bbc6b4045f",
                "preview": "Viewed video"
                " https://www.instagram.com/reel/SYNTHETIC_REEL_1/"
                " on instagram",
                "asat": datetime(2026, 3, 10, 14, 33, 45, tzinfo=UTC),
                "payload": {
                    "type": "View",
                    "published": "2026-03-10T14:33:45Z",
                    "object": {
                        "type": "Video",
                        "url": "https://www.instagram.com/reel/SYNTHETIC_REEL_1/",
                    },
                    "fibreKind": "View",
                },
            },
        ),
    ]

    def test_non_array_produces_no_rows(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        assert self.fixture_key is not None
        key = self.fixture_key
        storage.write(key, b'{"not": "an array"}')
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 0

    def test_record_fields_without_owner(self, extracted_records):
        record = extracted_records[0]
        assert record.author is None
        assert record.video_url == "https://www.instagram.com/reel/SYNTHETIC_VIDEO/"
        assert record.timestamp == 1770746034
        assert record.source is not None

    def test_record_fields_with_owner(self, extracted_records):
        record = extracted_records[1]
        assert record.author is None
        assert record.video_url == "https://www.instagram.com/reel/SYNTHETIC_REEL_1/"
        assert record.timestamp == 1773153225

    def test_payload_object_url(self, transformed_rows):
        obj = transformed_rows[0].payload["object"]
        assert obj["url"] == "https://www.instagram.com/reel/SYNTHETIC_VIDEO/"
        assert "attributedTo" not in obj

    def test_owner_ignored_in_v1(self, transformed_rows):
        obj = transformed_rows[1].payload["object"]
        assert obj["url"] == "https://www.instagram.com/reel/SYNTHETIC_REEL_1/"
        assert "attributedTo" not in obj

    def test_preview_includes_url(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Viewed video" in preview
        assert "SYNTHETIC_VIDEO" in preview

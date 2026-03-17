from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from context_use.providers.instagram.posts_viewed.pipe import (
    InstagramPostsViewedPipe,
    InstagramPostsViewedV0Pipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import AttributedToProfileMixin, PipeTestKit, PostObjectMixin
from tests.unit.etl.instagram.conftest import (
    INSTAGRAM_POSTS_VIEWED_V0_JSON,
    INSTAGRAM_POSTS_VIEWED_V1_JSON,
)


class TestInstagramPostsViewedV0Pipe(
    PostObjectMixin, AttributedToProfileMixin, PipeTestKit
):
    pipe_class = InstagramPostsViewedV0Pipe
    expected_extract_count = 3
    expected_transform_count = 3
    fixture_data = INSTAGRAM_POSTS_VIEWED_V0_JSON
    fixture_key = "archive/ads_information/ads_and_topics/posts_viewed.json"
    expected_fibre_kind = "View"
    snapshot_cases = [
        (
            {
                "impressions_history_posts_seen": [
                    {
                        "string_map_data": {
                            "Author": {"value": "synthetic_foodie"},
                            "Time": {"timestamp": 1743840091},
                        }
                    }
                ]
            },
            {
                "unique_key": "f2a8ea8e8cd10028",
                "preview": "Viewed post by synthetic_foodie on instagram",
                "asat": datetime(2025, 4, 5, 8, 1, 31, tzinfo=UTC),
                "payload": {
                    "type": "View",
                    "published": "2025-04-05T08:01:31Z",
                    "object": {
                        "type": "Note",
                        "attributedTo": {
                            "type": "Profile",
                            "name": "synthetic_foodie",
                            "url": "https://www.instagram.com/synthetic_foodie",
                        },
                        "fibreKind": "Post",
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
        assert record.author == "synthetic_foodie"
        assert record.timestamp == 1743840091
        assert record.post_url is None
        assert record.source is not None

    def test_attribution_name_and_url(self, transformed_rows):
        attr = transformed_rows[0].payload["object"]["attributedTo"]
        assert attr["name"] == "synthetic_foodie"
        assert attr["url"] == "https://www.instagram.com/synthetic_foodie"

    def test_preview_includes_post_and_author(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Viewed post" in preview
        assert "synthetic_foodie" in preview
        assert "instagram" in preview.lower()


class TestInstagramPostsViewedV1Pipe(PostObjectMixin, PipeTestKit):
    pipe_class = InstagramPostsViewedPipe
    expected_extract_count = 2
    expected_transform_count = 2
    fixture_data = INSTAGRAM_POSTS_VIEWED_V1_JSON
    fixture_key = "archive/ads_information/ads_and_topics/posts_viewed.json"
    expected_fibre_kind = "View"
    snapshot_cases = [
        (
            [
                {
                    "timestamp": 1771848416,
                    "media": [],
                    "label_values": [
                        {
                            "label": "URL",
                            "value": "https://www.instagram.com/p/SYNTHETIC_POST_1/",
                            "href": "https://www.instagram.com/p/SYNTHETIC_POST_1/",
                        },
                        {
                            "dict": [
                                {
                                    "dict": [
                                        {
                                            "label": "URL",
                                            "value": "https://linktr.ee/synthetic_artist",
                                        },
                                        {
                                            "label": "Name",
                                            "value": "Synthetic Artist",
                                        },
                                        {
                                            "label": "Username",
                                            "value": "synthetic_artist",
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
                "unique_key": "c07e119b4679385c",
                "preview": "Viewed post"
                " https://www.instagram.com/p/SYNTHETIC_POST_1/"
                " by synthetic_artist on instagram",
                "asat": datetime(2026, 2, 23, 12, 6, 56, tzinfo=UTC),
                "payload": {
                    "type": "View",
                    "published": "2026-02-23T12:06:56Z",
                    "object": {
                        "type": "Note",
                        "attributedTo": {
                            "type": "Profile",
                            "name": "synthetic_artist",
                            "url": "https://www.instagram.com/synthetic_artist",
                        },
                        "url": "https://www.instagram.com/p/SYNTHETIC_POST_1/",
                        "fibreKind": "Post",
                    },
                    "fibreKind": "View",
                },
            },
        ),
        (
            [
                {
                    "timestamp": 1771762100,
                    "media": [],
                    "label_values": [
                        {
                            "label": "URL",
                            "value": "https://www.instagram.com/p/SYNTHETIC_POST_2/",
                            "href": "https://www.instagram.com/p/SYNTHETIC_POST_2/",
                        },
                    ],
                }
            ],
            {
                "unique_key": "835351bc2837ba93",
                "preview": "Viewed post"
                " https://www.instagram.com/p/SYNTHETIC_POST_2/"
                " on instagram",
                "asat": datetime(2026, 2, 22, 12, 8, 20, tzinfo=UTC),
                "payload": {
                    "type": "View",
                    "published": "2026-02-22T12:08:20Z",
                    "object": {
                        "type": "Note",
                        "url": "https://www.instagram.com/p/SYNTHETIC_POST_2/",
                        "fibreKind": "Post",
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

    def test_record_fields_with_owner(self, extracted_records):
        record = extracted_records[0]
        assert record.author == "synthetic_artist"
        assert record.post_url == "https://www.instagram.com/p/SYNTHETIC_POST_1/"
        assert record.timestamp == 1771848416
        assert record.source is not None

    def test_record_fields_without_owner(self, extracted_records):
        record = extracted_records[1]
        assert record.author is None
        assert record.post_url == "https://www.instagram.com/p/SYNTHETIC_POST_2/"
        assert record.timestamp == 1771762100

    def test_payload_object_url(self, transformed_rows):
        assert (
            transformed_rows[0].payload["object"]["url"]
            == "https://www.instagram.com/p/SYNTHETIC_POST_1/"
        )

    def test_payload_has_attributed_to_from_owner(self, transformed_rows):
        attr = transformed_rows[0].payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "synthetic_artist"
        assert attr["url"] == "https://www.instagram.com/synthetic_artist"

    def test_payload_no_attributed_to_when_no_owner(self, transformed_rows):
        assert "attributedTo" not in transformed_rows[1].payload["object"]

    def test_preview_includes_url(self, transformed_rows):
        preview = transformed_rows[1].preview
        assert "Viewed post" in preview
        assert "SYNTHETIC_POST_2" in preview

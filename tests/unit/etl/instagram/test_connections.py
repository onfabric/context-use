from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from context_use.providers.instagram.connections.pipe import (
    InstagramFollowersPipe,
    InstagramFollowingPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.instagram.conftest import (
    INSTAGRAM_FOLLOWERS_JSON,
    INSTAGRAM_FOLLOWING_JSON,
)


class TestInstagramFollowersPipe(PipeTestKit):
    pipe_class = InstagramFollowersPipe
    expected_extract_count = 2
    expected_transform_count = 2
    expected_fibre_kind = "FollowedBy"
    fixture_data = INSTAGRAM_FOLLOWERS_JSON
    fixture_key = "archive/connections/followers_and_following/followers_1.json"
    snapshot_cases = [
        (
            [
                {
                    "title": "",
                    "media_list_data": [],
                    "string_list_data": [
                        {
                            "href": "https://www.instagram.com/synthetic_follower_snapshot",
                            "value": "synthetic_follower_snapshot",
                            "timestamp": 1749947057,
                        }
                    ],
                }
            ],
            {
                "preview": "Followed by synthetic_follower_snapshot on instagram",
                "asat": datetime(2025, 6, 15, 0, 24, 17, tzinfo=UTC),
                "payload": {
                    "fibreKind": "FollowedBy",
                    "type": "Follow",
                    "published": "2025-06-15T00:24:17Z",
                    "actor": {
                        "name": "synthetic_follower_snapshot",
                        "type": "Person",
                        "url": "https://www.instagram.com/synthetic_follower_snapshot",
                    },
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

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.username == "synthetic_follower_1"
        assert record.profile_url == "https://www.instagram.com/synthetic_follower_1"
        assert record.timestamp == 1768003156
        assert record.source is not None

    def test_payload_actor_is_person(self, transformed_rows):
        actor = transformed_rows[0].payload["actor"]
        assert actor["type"] == "Person"
        assert actor["name"] == "synthetic_follower_1"
        assert "instagram.com/synthetic_follower_1" in actor["url"]

    def test_preview_includes_followed_by(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Followed by" in preview
        assert "synthetic_follower_1" in preview
        assert "instagram" in preview.lower()

    def test_glob_pattern_has_wildcard(self):
        """Confirm the glob pattern matches followers_1.json, followers_2.json, etc."""
        assert "*" in InstagramFollowersPipe.archive_path_pattern


class TestInstagramFollowingPipe(PipeTestKit):
    pipe_class = InstagramFollowingPipe
    expected_extract_count = 2
    expected_transform_count = 2
    expected_fibre_kind = "Following"
    fixture_data = INSTAGRAM_FOLLOWING_JSON
    fixture_key = "archive/connections/followers_and_following/following.json"
    snapshot_cases = [
        (
            {
                "relationships_following": [
                    {
                        "title": "",
                        "media_list_data": [],
                        "string_list_data": [
                            {
                                "href": "https://www.instagram.com/synthetic_following_snapshot",
                                "value": "synthetic_following_snapshot",
                                "timestamp": 1749319371,
                            }
                        ],
                    }
                ]
            },
            {
                "preview": "Following synthetic_following_snapshot on instagram",
                "asat": datetime(2025, 6, 7, 18, 2, 51, tzinfo=UTC),
                "payload": {
                    "fibreKind": "Following",
                    "type": "Follow",
                    "published": "2025-06-07T18:02:51Z",
                    "object": {
                        "name": "synthetic_following_snapshot",
                        "type": "Profile",
                        "url": "https://www.instagram.com/synthetic_following_snapshot",
                    },
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
        assert record.username == "synthetic_foodblog"
        assert record.profile_url == "https://www.instagram.com/_u/synthetic_foodblog"
        assert record.timestamp == 1770897717
        assert record.source is not None

    def test_payload_object_is_profile(self, transformed_rows):
        obj = transformed_rows[0].payload["object"]
        assert obj["type"] == "Profile"
        assert obj["name"] == "synthetic_foodblog"
        assert "instagram.com" in obj["url"]

    def test_preview_includes_following(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Following" in preview
        assert "synthetic_foodblog" in preview
        assert "instagram" in preview.lower()

    def test_username_from_title(self, extracted_records):
        """Username should come from the ``title`` field, not parsed from href."""
        assert extracted_records[0].username == "synthetic_foodblog"

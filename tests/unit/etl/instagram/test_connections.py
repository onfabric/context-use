from __future__ import annotations

from context_use.providers.instagram.connections import (
    InstagramFollowersPipe,
    InstagramFollowingPipe,
)
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

from __future__ import annotations

from context_use.providers.instagram.likes import (
    InstagramLikedPostsPipe,
    InstagramLikedPostsV0Pipe,
    InstagramStoryLikesPipe,
    InstagramStoryLikesV0Pipe,
)
from context_use.testing import PipeTestKit
from tests.unit.etl.instagram.conftest import (
    INSTAGRAM_LIKED_POSTS_V0_JSON,
    INSTAGRAM_LIKED_POSTS_V1_JSON,
    INSTAGRAM_STORY_LIKES_V0_JSON,
    INSTAGRAM_STORY_LIKES_V1_JSON,
)


class TestInstagramLikedPostsV0Pipe(PipeTestKit):
    pipe_class = InstagramLikedPostsV0Pipe
    expected_extract_count = 2
    expected_transform_count = 2
    fixture_data = INSTAGRAM_LIKED_POSTS_V0_JSON
    fixture_key = "archive/your_instagram_activity/likes/liked_posts.json"
    expected_fibre_kind = "Reaction"

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.title == "synthetic_foodblog"
        assert record.href == "https://www.instagram.com/reel/XXXXXXXXXXX/"
        assert record.timestamp == 1770775983
        assert record.source is not None

    def test_payload_object_is_post(self, transformed_rows):
        for row in transformed_rows:
            obj = row.payload["object"]
            assert obj["type"] == "Note"  # FibrePost extends Note
            assert obj["fibreKind"] == "Post"

    def test_payload_has_attributed_to(self, transformed_rows):
        attr = transformed_rows[0].payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "synthetic_foodblog"

    def test_payload_has_post_url(self, transformed_rows):
        obj = transformed_rows[0].payload["object"]
        assert "url" in obj
        assert "XXXXXXXXXXX" in obj["url"]

    def test_preview_includes_liked(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Liked" in preview
        assert "synthetic_foodblog" in preview
        assert "instagram" in preview.lower()


class TestInstagramLikedPostsV1Pipe(PipeTestKit):
    pipe_class = InstagramLikedPostsPipe
    expected_extract_count = 2
    expected_transform_count = 2
    fixture_data = INSTAGRAM_LIKED_POSTS_V1_JSON
    fixture_key = "archive/your_instagram_activity/likes/liked_posts.json"
    expected_fibre_kind = "Reaction"

    def test_record_fields_with_owner(self, extracted_records):
        record = extracted_records[0]
        assert record.title == "synthetic_foodblog"
        assert record.href == "https://www.instagram.com/reel/XXXXXXXXXXX/"
        assert record.timestamp == 1770775983
        assert record.source is not None

    def test_record_fields_second(self, extracted_records):
        record = extracted_records[1]
        assert record.title == "synthetic_traveler"
        assert record.href == "https://www.instagram.com/p/YYYYYYYYYYY/"
        assert record.timestamp == 1770683481

    def test_payload_object_is_post_with_url(self, transformed_rows):
        obj = transformed_rows[0].payload["object"]
        assert obj["type"] == "Note"  # FibrePost extends Note
        assert obj["fibreKind"] == "Post"
        assert obj["url"] == "https://www.instagram.com/reel/XXXXXXXXXXX/"

    def test_payload_has_attributed_to_from_owner(self, transformed_rows):
        attr = transformed_rows[0].payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "synthetic_foodblog"

    def test_preview_includes_liked(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Liked" in preview
        assert "synthetic_foodblog" in preview


class TestInstagramStoryLikesV0Pipe(PipeTestKit):
    pipe_class = InstagramStoryLikesV0Pipe
    expected_extract_count = 1
    expected_transform_count = 1
    fixture_data = INSTAGRAM_STORY_LIKES_V0_JSON
    fixture_key = "archive/your_instagram_activity/story_interactions/story_likes.json"
    expected_fibre_kind = "Reaction"

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.title == "synthetic_photographer"
        assert record.href is None  # story likes have no href
        assert record.timestamp == 1771028852

    def test_payload_object_is_post_without_url(self, transformed_rows):
        obj = transformed_rows[0].payload["object"]
        assert obj["type"] == "Note"
        assert obj["fibreKind"] == "Post"
        assert "url" not in obj

    def test_payload_has_attributed_to(self, transformed_rows):
        attr = transformed_rows[0].payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "synthetic_photographer"

    def test_preview_includes_liked(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Liked" in preview
        assert "synthetic_photographer" in preview


class TestInstagramStoryLikesV1Pipe(PipeTestKit):
    pipe_class = InstagramStoryLikesPipe
    expected_extract_count = 1
    expected_transform_count = 1
    fixture_data = INSTAGRAM_STORY_LIKES_V1_JSON
    fixture_key = "archive/your_instagram_activity/story_interactions/story_likes.json"
    expected_fibre_kind = "Reaction"

    def test_record_fields_with_owner(self, extracted_records):
        record = extracted_records[0]
        assert record.title == "synthetic_photographer"
        assert record.href is None  # story likes still have no URL
        assert record.timestamp == 1771028852
        assert record.source is not None

    def test_payload_object_is_post_without_url(self, transformed_rows):
        obj = transformed_rows[0].payload["object"]
        assert obj["type"] == "Note"
        assert obj["fibreKind"] == "Post"
        assert "url" not in obj

    def test_payload_has_attributed_to_from_owner(self, transformed_rows):
        attr = transformed_rows[0].payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "synthetic_photographer"

    def test_preview_includes_liked(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Liked" in preview
        assert "synthetic_photographer" in preview

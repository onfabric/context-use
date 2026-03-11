from __future__ import annotations

from context_use.providers.instagram.likes import (
    InstagramLikedPostsPipe,
    InstagramLikedPostsV0Pipe,
    InstagramStoryLikesPipe,
    InstagramStoryLikesV0Pipe,
)
from context_use.testing import AttributedToProfileMixin, PipeTestKit, PostObjectMixin
from tests.unit.etl.instagram.conftest import (
    INSTAGRAM_LIKED_POSTS_V0_JSON,
    INSTAGRAM_LIKED_POSTS_V1_JSON,
    INSTAGRAM_STORY_LIKES_V0_JSON,
    INSTAGRAM_STORY_LIKES_V1_JSON,
)


class TestInstagramLikedPostsV0Pipe(
    PostObjectMixin, AttributedToProfileMixin, PipeTestKit
):
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

    def test_attribution_name(self, transformed_rows):
        assert (
            transformed_rows[0].payload["object"]["attributedTo"]["name"]
            == "synthetic_foodblog"
        )

    def test_payload_has_post_url(self, transformed_rows):
        obj = transformed_rows[0].payload["object"]
        assert "url" in obj
        assert "XXXXXXXXXXX" in obj["url"]

    def test_preview_includes_liked(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Liked" in preview
        assert "synthetic_foodblog" in preview
        assert "instagram" in preview.lower()


class TestInstagramLikedPostsV1Pipe(
    PostObjectMixin, AttributedToProfileMixin, PipeTestKit
):
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

    def test_payload_object_url(self, transformed_rows):
        assert (
            transformed_rows[0].payload["object"]["url"]
            == "https://www.instagram.com/reel/XXXXXXXXXXX/"
        )

    def test_attribution_name(self, transformed_rows):
        assert (
            transformed_rows[0].payload["object"]["attributedTo"]["name"]
            == "synthetic_foodblog"
        )

    def test_preview_includes_liked(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Liked" in preview
        assert "synthetic_foodblog" in preview


class TestInstagramStoryLikesV0Pipe(
    PostObjectMixin, AttributedToProfileMixin, PipeTestKit
):
    pipe_class = InstagramStoryLikesV0Pipe
    expected_extract_count = 1
    expected_transform_count = 1
    fixture_data = INSTAGRAM_STORY_LIKES_V0_JSON
    fixture_key = "archive/your_instagram_activity/story_interactions/story_likes.json"
    expected_fibre_kind = "Reaction"

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.title == "synthetic_photographer"
        assert record.href is None
        assert record.timestamp == 1771028852

    def test_payload_object_has_no_url(self, transformed_rows):
        assert "url" not in transformed_rows[0].payload["object"]

    def test_attribution_name(self, transformed_rows):
        assert (
            transformed_rows[0].payload["object"]["attributedTo"]["name"]
            == "synthetic_photographer"
        )

    def test_preview_includes_liked(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Liked" in preview
        assert "synthetic_photographer" in preview


class TestInstagramStoryLikesV1Pipe(
    PostObjectMixin, AttributedToProfileMixin, PipeTestKit
):
    pipe_class = InstagramStoryLikesPipe
    expected_extract_count = 1
    expected_transform_count = 1
    fixture_data = INSTAGRAM_STORY_LIKES_V1_JSON
    fixture_key = "archive/your_instagram_activity/story_interactions/story_likes.json"
    expected_fibre_kind = "Reaction"

    def test_record_fields_with_owner(self, extracted_records):
        record = extracted_records[0]
        assert record.title == "synthetic_photographer"
        assert record.href is None
        assert record.timestamp == 1771028852
        assert record.source is not None

    def test_payload_object_has_no_url(self, transformed_rows):
        assert "url" not in transformed_rows[0].payload["object"]

    def test_attribution_name(self, transformed_rows):
        assert (
            transformed_rows[0].payload["object"]["attributedTo"]["name"]
            == "synthetic_photographer"
        )

    def test_preview_includes_liked(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Liked" in preview
        assert "synthetic_photographer" in preview

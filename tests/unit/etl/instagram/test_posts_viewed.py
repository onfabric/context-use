from __future__ import annotations

from context_use.providers.instagram.posts_viewed import (
    InstagramPostsViewedPipe,
    InstagramPostsViewedV0Pipe,
)
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

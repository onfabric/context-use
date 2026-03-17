from __future__ import annotations

from context_use.providers.airbnb.reviews.pipe import AirbnbReviewsPipe
from context_use.testing import PipeTestKit
from tests.unit.etl.airbnb.conftest import AIRBNB_REVIEWS_JSON


class TestAirbnbReviewsPipe(PipeTestKit):
    pipe_class = AirbnbReviewsPipe
    expected_extract_count = 1
    expected_transform_count = 1
    expected_fibre_kind = "Comment"
    fixture_data = AIRBNB_REVIEWS_JSON
    fixture_key = "archive/json/reviews.json"

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.review_id == 901977635384836330
        assert record.rating == 4
        assert record.comment.startswith("Great location")
        assert record.bookable_id == 5043698985
        assert record.comment_language == "en"
        assert record.source is not None

    def test_preview_includes_comment(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Commented" in preview
        assert "Great location" in preview
        assert "listing" in preview
        assert "Airbnb" in preview

    def test_payload_has_in_reply_to(self, transformed_rows):
        row = transformed_rows[0]
        assert row.payload["inReplyTo"] is not None
        assert row.payload["inReplyTo"]["type"] == "Page"
        assert "5043698985" in row.payload["inReplyTo"]["url"]

    def test_payload_object_is_note(self, transformed_rows):
        row = transformed_rows[0]
        assert row.payload["object"]["type"] == "Note"
        assert "Great location" in row.payload["object"]["content"]

from __future__ import annotations

from context_use.providers.airbnb.wishlists.pipe import AirbnbWishlistsPipe
from context_use.testing import PipeTestKit
from tests.unit.etl.airbnb.conftest import AIRBNB_WISHLISTS_JSON


class TestAirbnbWishlistsPipe(PipeTestKit):
    pipe_class = AirbnbWishlistsPipe
    expected_extract_count = 3
    expected_transform_count = 3
    expected_fibre_kind = "AddToCollection"
    fixture_data = AIRBNB_WISHLISTS_JSON
    fixture_key = "archive/json/wishlists.json"

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.wishlist_name == "Bangalore"
        assert record.pdp_id == "1109956002377193237"
        assert record.pdp_type == "HOME"
        assert record.check_in == "2024-02-28"
        assert record.source is not None

    def test_record_without_dates(self, extracted_records):
        record = extracted_records[1]
        assert record.wishlist_name == "Bangalore"
        assert record.check_in is None
        assert record.check_out is None

    def test_flattening(self, extracted_records):
        names = [r.wishlist_name for r in extracted_records]
        assert names.count("Bangalore") == 2
        assert names.count("Paris") == 1

    def test_preview_includes_wishlist_name(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Bangalore" in preview
        assert "Airbnb" in preview

    def test_payload_target_is_collection(self, transformed_rows):
        for row in transformed_rows:
            assert row.payload["target"]["type"] == "Collection"
            assert row.payload["target"]["name"] in ("Bangalore", "Paris")

    def test_payload_object_is_page(self, transformed_rows):
        for row in transformed_rows:
            assert row.payload["object"]["type"] == "Page"
            assert "airbnb.com/rooms/" in row.payload["object"]["url"]

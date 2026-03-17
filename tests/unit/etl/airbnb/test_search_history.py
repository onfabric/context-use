from __future__ import annotations

from context_use.providers.airbnb.search_history.pipe import AirbnbSearchHistoryPipe
from context_use.testing import PipeTestKit
from tests.unit.etl.airbnb.conftest import AIRBNB_SEARCH_HISTORY_JSON


class TestAirbnbSearchHistoryPipe(PipeTestKit):
    pipe_class = AirbnbSearchHistoryPipe
    expected_extract_count = 3
    expected_transform_count = 3
    expected_fibre_kind = "Search"
    fixture_data = AIRBNB_SEARCH_HISTORY_JSON
    fixture_key = "archive/json/search_history.json"

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.city == "Paris"
        assert record.country == "France"
        assert record.number_of_guests == 2
        assert record.number_of_nights == 3
        assert record.time_of_search == "2023-04-25 20:36:16"
        assert record.source is not None

    def test_record_without_city(self, extracted_records):
        record = extracted_records[2]
        assert record.city is None
        assert record.raw_location is None
        assert record.number_of_guests == 4

    def test_preview_includes_city(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Paris" in preview
        assert "Airbnb" in preview

    def test_preview_without_location_uses_unknown(self, transformed_rows):
        preview = transformed_rows[2].preview
        assert "unknown" in preview

    def test_payload_object_is_page(self, transformed_rows):
        for row in transformed_rows:
            assert row.payload["object"]["type"] == "Page"

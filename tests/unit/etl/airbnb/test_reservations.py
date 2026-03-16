from __future__ import annotations

from context_use.providers.airbnb.reservations.pipe import AirbnbReservationsPipe
from context_use.testing import PipeTestKit
from tests.unit.etl.airbnb.conftest import AIRBNB_RESERVATIONS_JSON


class TestAirbnbReservationsPipe(PipeTestKit):
    pipe_class = AirbnbReservationsPipe
    expected_extract_count = 3
    expected_transform_count = 3
    expected_fibre_kind = "View"
    fixture_data = AIRBNB_RESERVATIONS_JSON
    fixture_key = "archive/json/reservations.json"

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.confirmation_code == "HM4KR5KA2J"
        assert record.nights == 3
        assert record.start_date == "2023-05-26"
        assert record.status == "accepted"
        assert record.message is None
        assert record.source is not None

    def test_record_with_message(self, extracted_records):
        record = extracted_records[1]
        assert record.message is not None
        assert "family" in record.message

    def test_cancelled_reservation(self, extracted_records):
        record = extracted_records[2]
        assert record.status == "cancelled"

    def test_preview_includes_stay_details(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "3-night stay" in preview
        assert "2023-05-26" in preview
        assert "Airbnb" in preview

    def test_payload_object_is_page(self, transformed_rows):
        for row in transformed_rows:
            assert row.payload["object"]["type"] == "Page"

    def test_payload_has_hosting_url(self, transformed_rows):
        row = transformed_rows[0]
        assert "airbnb.com/rooms/" in row.payload["object"]["url"]

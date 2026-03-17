from __future__ import annotations

from context_use.providers.airbnb.messages.pipe import AirbnbMessagesPipe
from context_use.testing import PipeTestKit
from tests.unit.etl.airbnb.conftest import AIRBNB_MESSAGES_JSON


class TestAirbnbMessagesPipe(PipeTestKit):
    pipe_class = AirbnbMessagesPipe
    expected_extract_count = 2
    expected_transform_count = 2
    fixture_data = AIRBNB_MESSAGES_JSON
    fixture_key = "archive/json/messages.json"

    def test_sent_message(self, extracted_records):
        record = extracted_records[0]
        assert record.account_type == "guest"
        assert "arriving around 3pm" in record.text

    def test_received_message(self, extracted_records):
        record = extracted_records[1]
        assert record.account_type == "host"

    def test_service_messages_filtered(self, extracted_records):
        for record in extracted_records:
            assert record.account_type in ("guest", "host")

    def test_sent_preview(self, transformed_rows):
        row = transformed_rows[0]
        assert row.payload["fibreKind"] == "SendMessage"
        assert "Sent" in row.preview

    def test_received_preview(self, transformed_rows):
        row = transformed_rows[1]
        assert row.payload["fibreKind"] == "ReceiveMessage"
        assert row.payload["actor"]["type"] == "Person"
        assert "Received" in row.preview

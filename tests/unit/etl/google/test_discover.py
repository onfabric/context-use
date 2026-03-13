from __future__ import annotations

from context_use.providers.google.discover.pipe import GoogleDiscoverPipe
from context_use.testing import PipeTestKit
from tests.unit.etl.google.conftest import GOOGLE_DISCOVER_JSON


class TestGoogleDiscoverPipe(PipeTestKit):
    pipe_class = GoogleDiscoverPipe
    expected_extract_count = 2
    expected_transform_count = 2
    expected_fibre_kind = "View"
    fixture_data = GOOGLE_DISCOVER_JSON
    fixture_key = "archive/Portability/My Activity/Discover/MyActivity.json"

    def test_feed_summary_filtered(self, extracted_records):
        """Feed summary records ('X cards in your feed') are dropped."""
        titles = [r.title for r in extracted_records]
        assert not any("cards in your feed" in t for t in titles)

    def test_preview_text(self, transformed_rows):
        previews = [r.preview for r in transformed_rows]
        assert all("Content From Discover" in p for p in previews)

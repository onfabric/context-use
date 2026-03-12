from __future__ import annotations

from context_use.providers.google.shopping.pipe import GoogleShoppingPipe
from context_use.testing import PipeTestKit
from tests.unit.etl.google.conftest import GOOGLE_SHOPPING_JSON


class TestGoogleShoppingPipe(PipeTestKit):
    pipe_class = GoogleShoppingPipe
    expected_extract_count = 3
    expected_transform_count = 3
    fixture_data = GOOGLE_SHOPPING_JSON
    fixture_key = "archive/Portability/My Activity/Shopping/MyActivity.json"

    def test_unrecognised_prefix_filtered(self, extracted_records):
        """Records with unknown prefixes ('Used') are dropped."""
        titles = [r.title for r in extracted_records]
        assert not any(t.startswith("Used") for t in titles)

    def test_search_and_view_payloads(self, transformed_rows):
        kinds = {r.payload["fibreKind"] for r in transformed_rows}
        assert "Search" in kinds
        assert "View" in kinds

    def test_shopping_urls_not_unwrapped(self, transformed_rows):
        """Shopping URLs are not google.com/url redirects — kept as-is."""
        for row in transformed_rows:
            url = row.payload["object"].get("url")
            if url:
                assert "google.com" in url

    def test_preview_text(self, transformed_rows):
        previews = [r.preview for r in transformed_rows]
        assert any("headphones" in p.lower() for p in previews)

from __future__ import annotations

from context_use.providers.google.lens.pipe import GoogleLensPipe
from context_use.testing import PipeTestKit
from tests.unit.etl.google.conftest import GOOGLE_LENS_JSON


class TestGoogleLensPipe(PipeTestKit):
    pipe_class = GoogleLensPipe
    expected_extract_count = 2
    expected_transform_count = 2
    expected_fibre_kind = "Search"
    fixture_data = GOOGLE_LENS_JSON
    fixture_key = "archive/Portability/My Activity/Google Lens/MyActivity.json"

    def test_bare_lens_search_filtered(self, extracted_records):
        """Bare 'Searched with Google Lens' records (no query) are dropped."""
        for r in extracted_records:
            assert r.title != "Searched with Google Lens"

    def test_lens_plus_query_extracted(self, transformed_rows):
        """'Searched with Google Lens + "query"' extracts the quoted query."""
        names = [row.payload["object"].get("name") for row in transformed_rows]
        assert "types of succulent plants" in names

    def test_searched_for_url_preserved(self, transformed_rows):
        """'Searched for ...' records keep the google.com/search URL."""
        urls = [row.payload["object"].get("url") for row in transformed_rows]
        assert any(u and "google.com/search" in u for u in urls)

    def test_preview_text(self, transformed_rows):
        previews = [r.preview for r in transformed_rows]
        assert any("succulent plants" in p for p in previews)

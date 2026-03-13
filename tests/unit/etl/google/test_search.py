from __future__ import annotations

from context_use.providers.google.search.pipe import (
    GoogleImageSearchPipe,
    GoogleSearchPipe,
    GoogleVideoSearchPipe,
)
from context_use.testing import PipeTestKit
from tests.unit.etl.google.conftest import (
    GOOGLE_IMAGE_SEARCH_JSON,
    GOOGLE_SEARCH_JSON,
    GOOGLE_VIDEO_SEARCH_JSON,
)


class TestGoogleSearchPipe(PipeTestKit):
    pipe_class = GoogleSearchPipe
    expected_extract_count = 3
    expected_transform_count = 3
    fixture_data = GOOGLE_SEARCH_JSON
    fixture_key = "archive/Portability/My Activity/Search/MyActivity.json"

    def test_unrecognised_prefix_filtered(self, extracted_records):
        """Records with unknown prefixes should be dropped in extract."""
        titles = [r.title for r in extracted_records]
        assert not any(t.startswith("Used") for t in titles)

    def test_search_and_view_payloads(self, transformed_rows):
        kinds = {r.payload["fibreKind"] for r in transformed_rows}
        assert "Search" in kinds
        assert "View" in kinds

    def test_redirect_url_unwrapped(self, transformed_rows):
        """Google /url redirect URLs should be unwrapped to the actual URL."""
        view_rows = [r for r in transformed_rows if r.payload["fibreKind"] == "View"]
        for row in view_rows:
            url = row.payload["object"].get("url")
            if url:
                assert "google.com/url" not in url

    def test_search_url_preserved(self, transformed_rows):
        """Non-redirect Google URLs (google.com/search) should be kept as-is."""
        search_rows = [
            r for r in transformed_rows if r.payload["fibreKind"] == "Search"
        ]
        for row in search_rows:
            url = row.payload["object"].get("url")
            if url and "google.com/search" in url:
                assert url.startswith("https://www.google.com/search")

    def test_preview_text(self, transformed_rows):
        previews = [r.preview for r in transformed_rows]
        assert any("python tutorials" in p for p in previews)


class TestGoogleVideoSearchPipe(PipeTestKit):
    pipe_class = GoogleVideoSearchPipe
    expected_extract_count = 2
    expected_transform_count = 2
    fixture_data = GOOGLE_VIDEO_SEARCH_JSON
    fixture_key = "archive/Portability/My Activity/Video Search/MyActivity.json"

    def test_payload_types(self, transformed_rows):
        kinds = {r.payload["fibreKind"] for r in transformed_rows}
        assert "Search" in kinds
        assert "View" in kinds


class TestGoogleImageSearchPipe(PipeTestKit):
    pipe_class = GoogleImageSearchPipe
    expected_extract_count = 2
    expected_transform_count = 2
    fixture_data = GOOGLE_IMAGE_SEARCH_JSON
    fixture_key = "archive/Portability/My Activity/Image Search/MyActivity.json"

    def test_payload_types(self, transformed_rows):
        kinds = {r.payload["fibreKind"] for r in transformed_rows}
        assert "Search" in kinds
        assert "View" in kinds

    def test_search_url_not_unwrapped(self, transformed_rows):
        """google.com/search URLs should be preserved, not have q= extracted."""
        search_rows = [
            r for r in transformed_rows if r.payload["fibreKind"] == "Search"
        ]
        assert len(search_rows) >= 1
        url = search_rows[0].payload["object"].get("url")
        assert url is not None
        assert "google.com/search" in url

    def test_redirect_url_unwrapped(self, transformed_rows):
        """google.com/url redirect URLs should be unwrapped."""
        view_rows = [r for r in transformed_rows if r.payload["fibreKind"] == "View"]
        assert len(view_rows) >= 1
        url = view_rows[0].payload["object"].get("url")
        assert url is not None
        assert "example.com" in url
        assert "google.com/url" not in url

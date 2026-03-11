from __future__ import annotations

from context_use.providers.google.youtube import GoogleYoutubePipe
from context_use.testing import PipeTestKit
from tests.unit.etl.google.conftest import GOOGLE_YOUTUBE_JSON


class TestGoogleYoutubePipe(PipeTestKit):
    pipe_class = GoogleYoutubePipe
    expected_extract_count = 7
    expected_transform_count = 7
    fixture_data = GOOGLE_YOUTUBE_JSON
    fixture_key = "archive/Portability/My Activity/YouTube/MyActivity.json"

    def test_unrecognised_prefix_filtered(self, extracted_records):
        """Records with unknown prefixes (e.g. 'Shared') are dropped."""
        titles = [r.title for r in extracted_records]
        assert not any(t.startswith("Shared") for t in titles)

    def test_all_fibre_kinds_present(self, transformed_rows):
        """Fixture covers all 6 fibre kinds."""
        kinds = {r.payload["fibreKind"] for r in transformed_rows}
        assert "Search" in kinds
        assert "View" in kinds
        assert "Reaction" in kinds
        assert "Following" in kinds
        assert "AddToCollection" in kinds

    def test_watched_produces_view_with_video(self, transformed_rows):
        """'Watched' records produce FibreViewObject with Video object."""
        view_rows = [r for r in transformed_rows if r.payload["fibreKind"] == "View"]
        assert len(view_rows) == 2
        for row in view_rows:
            assert row.payload["object"]["type"] == "Video"

    def test_watched_with_subtitles_has_attribution(self, transformed_rows):
        """'Watched' with subtitles includes channel attribution."""
        view_rows = [r for r in transformed_rows if r.payload["fibreKind"] == "View"]
        attributed = [r for r in view_rows if r.payload["object"].get("attributedTo")]
        assert len(attributed) == 1
        attr = attributed[0].payload["object"]["attributedTo"]
        assert attr["name"] == "Cooking Channel"
        assert attr["type"] == "Person"

    def test_searched_produces_search_with_page(self, transformed_rows):
        """'Searched for' records produce FibreSearch with Page object."""
        search_rows = [
            r for r in transformed_rows if r.payload["fibreKind"] == "Search"
        ]
        assert len(search_rows) == 1
        assert search_rows[0].payload["object"]["type"] == "Page"
        assert "pasta recipes" in search_rows[0].preview

    def test_liked_produces_reaction_like(self, transformed_rows):
        """'Liked' records produce FibreReaction with type=Like."""
        like_rows = [
            r
            for r in transformed_rows
            if r.payload["fibreKind"] == "Reaction" and r.payload["type"] == "Like"
        ]
        assert len(like_rows) == 1
        assert like_rows[0].payload["object"]["type"] == "Video"

    def test_disliked_produces_reaction_dislike(self, transformed_rows):
        """'Disliked' records produce FibreReaction with type=Dislike."""
        dislike_rows = [
            r
            for r in transformed_rows
            if r.payload["fibreKind"] == "Reaction" and r.payload["type"] == "Dislike"
        ]
        assert len(dislike_rows) == 1
        assert dislike_rows[0].payload["object"]["type"] == "Video"
        assert "Bad Chef" in (
            dislike_rows[0].payload["object"].get("attributedTo", {}).get("name", "")
        )

    def test_subscribed_produces_following(self, transformed_rows):
        """'Subscribed to' records produce FibreFollowing."""
        follow_rows = [
            r for r in transformed_rows if r.payload["fibreKind"] == "Following"
        ]
        assert len(follow_rows) == 1
        assert follow_rows[0].payload["object"]["type"] == "Profile"
        assert follow_rows[0].payload["object"]["name"] == ("Cooking Channel")

    def test_saved_produces_add_to_collection(self, transformed_rows):
        """'Saved' records produce FibreAddObjectToCollection."""
        saved_rows = [
            r for r in transformed_rows if r.payload["fibreKind"] == "AddToCollection"
        ]
        assert len(saved_rows) == 1
        assert saved_rows[0].payload["object"]["type"] == "Video"
        target = saved_rows[0].payload["target"]
        assert target["fibreKind"] == "CollectionFavourites"

    def test_preview_text(self, transformed_rows):
        """Previews contain meaningful content."""
        previews = [r.preview for r in transformed_rows]
        assert all(p for p in previews), "All previews should be non-empty"
        assert any("pasta" in p.lower() for p in previews)

    def test_youtube_urls_not_unwrapped(self, transformed_rows):
        """YouTube URLs should pass through clean_url() unchanged."""
        for row in transformed_rows:
            obj = row.payload.get("object", {})
            url = obj.get("url") if isinstance(obj, dict) else None
            if url and "youtube.com" in url:
                assert "google.com/url" not in url

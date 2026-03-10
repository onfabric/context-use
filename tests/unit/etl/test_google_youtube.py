
import json
from pathlib import Path

import pytest

from context_use.providers.google.youtube import GoogleYoutubePipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import GOOGLE_YOUTUBE_JSON

_BASE = "Portability/My Activity"


def _write_fixture(tmp_path: Path, data: list[dict]) -> tuple[DiskStorage, str]:
    storage = DiskStorage(str(tmp_path / "store"))
    key = f"archive/{_BASE}/YouTube/MyActivity.json"
    storage.write(key, json.dumps(data).encode())
    return storage, key


class TestGoogleYoutubePipe(PipeTestKit):
    pipe_class = GoogleYoutubePipe
    # 8 records in fixture, 1 has unrecognised prefix ("Shared") → 7 extracted
    expected_extract_count = 7
    expected_transform_count = 7

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        return _write_fixture(tmp_path, GOOGLE_YOUTUBE_JSON)

    def test_unrecognised_prefix_filtered(self, pipe_fixture):
        """Records with unknown prefixes (e.g. 'Shared') are dropped."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        records = list(pipe.extract(task, storage))
        titles = [r.title for r in records]
        assert not any(t.startswith("Shared") for t in titles)

    def test_all_fibre_kinds_present(self, pipe_fixture):
        """Fixture covers all 6 fibre kinds."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        kinds = {r.payload["fibreKind"] for r in rows}
        assert "Search" in kinds
        assert "View" in kinds
        assert "Reaction" in kinds
        assert "Following" in kinds
        assert "AddToCollection" in kinds

    def test_watched_produces_view_with_video(self, pipe_fixture):
        """'Watched' records produce FibreViewObject with Video object."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        view_rows = [r for r in rows if r.payload["fibreKind"] == "View"]
        assert len(view_rows) == 2
        for row in view_rows:
            assert row.payload["object"]["type"] == "Video"

    def test_watched_with_subtitles_has_attribution(self, pipe_fixture):
        """'Watched' with subtitles includes channel attribution."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        view_rows = [r for r in rows if r.payload["fibreKind"] == "View"]
        # First Watched has subtitles, second (ad) does not
        attributed = [r for r in view_rows if r.payload["object"].get("attributedTo")]
        assert len(attributed) == 1
        attr = attributed[0].payload["object"]["attributedTo"]
        assert attr["name"] == "Cooking Channel"
        assert attr["type"] == "Person"

    def test_searched_produces_search_with_page(self, pipe_fixture):
        """'Searched for' records produce FibreSearch with Page object."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        search_rows = [r for r in rows if r.payload["fibreKind"] == "Search"]
        assert len(search_rows) == 1
        assert search_rows[0].payload["object"]["type"] == "Page"
        assert "pasta recipes" in search_rows[0].preview

    def test_liked_produces_reaction_like(self, pipe_fixture):
        """'Liked' records produce FibreReaction with type=Like."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        like_rows = [
            r
            for r in rows
            if r.payload["fibreKind"] == "Reaction" and r.payload["type"] == "Like"
        ]
        assert len(like_rows) == 1
        assert like_rows[0].payload["object"]["type"] == "Video"

    def test_disliked_produces_reaction_dislike(self, pipe_fixture):
        """'Disliked' records produce FibreReaction with type=Dislike."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        dislike_rows = [
            r
            for r in rows
            if r.payload["fibreKind"] == "Reaction" and r.payload["type"] == "Dislike"
        ]
        assert len(dislike_rows) == 1
        assert dislike_rows[0].payload["object"]["type"] == "Video"
        assert "Bad Chef" in (
            dislike_rows[0].payload["object"].get("attributedTo", {}).get("name", "")
        )

    def test_subscribed_produces_following(self, pipe_fixture):
        """'Subscribed to' records produce FibreFollowing."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        follow_rows = [r for r in rows if r.payload["fibreKind"] == "Following"]
        assert len(follow_rows) == 1
        assert follow_rows[0].payload["object"]["type"] == "Profile"
        assert follow_rows[0].payload["object"]["name"] == ("Cooking Channel")

    def test_saved_produces_add_to_collection(self, pipe_fixture):
        """'Saved' records produce FibreAddObjectToCollection."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        saved_rows = [r for r in rows if r.payload["fibreKind"] == "AddToCollection"]
        assert len(saved_rows) == 1
        assert saved_rows[0].payload["object"]["type"] == "Video"
        target = saved_rows[0].payload["target"]
        assert target["fibreKind"] == "CollectionFavourites"

    def test_preview_text(self, pipe_fixture):
        """Previews contain meaningful content."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        previews = [r.preview for r in rows]
        assert all(p for p in previews), "All previews should be non-empty"
        assert any("pasta" in p.lower() for p in previews)

    def test_youtube_urls_not_unwrapped(self, pipe_fixture):
        """YouTube URLs should pass through clean_url() unchanged."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)
        rows = list(pipe.run(task, storage))
        for row in rows:
            obj = row.payload.get("object", {})
            url = obj.get("url") if isinstance(obj, dict) else None
            if url and "youtube.com" in url:
                assert "google.com/url" not in url

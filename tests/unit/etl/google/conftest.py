from __future__ import annotations

from context_use.testing.fixtures import load_fixture

_BASE = "users/alice/google/v1/Portability/My Activity"

GOOGLE_SEARCH_JSON: list[dict] = load_fixture(f"{_BASE}/Search/MyActivity.json")
GOOGLE_VIDEO_SEARCH_JSON: list[dict] = load_fixture(
    f"{_BASE}/Video Search/MyActivity.json"
)
GOOGLE_IMAGE_SEARCH_JSON: list[dict] = load_fixture(
    f"{_BASE}/Image Search/MyActivity.json"
)
GOOGLE_YOUTUBE_JSON: list[dict] = load_fixture(f"{_BASE}/YouTube/MyActivity.json")
GOOGLE_SHOPPING_JSON: list[dict] = load_fixture(f"{_BASE}/Shopping/MyActivity.json")
GOOGLE_DISCOVER_JSON: list[dict] = load_fixture(f"{_BASE}/Discover/MyActivity.json")
GOOGLE_LENS_JSON: list[dict] = load_fixture(f"{_BASE}/Google Lens/MyActivity.json")

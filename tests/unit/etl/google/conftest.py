from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parents[3] / "fixtures"
ALICE_GOOGLE_DIR = FIXTURES_DIR / "users" / "alice" / "google" / "v1"

GOOGLE_SEARCH_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR / "Portability" / "My Activity" / "Search" / "MyActivity.json"
    ).read_text()
)

GOOGLE_VIDEO_SEARCH_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR
        / "Portability"
        / "My Activity"
        / "Video Search"
        / "MyActivity.json"
    ).read_text()
)

GOOGLE_IMAGE_SEARCH_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR
        / "Portability"
        / "My Activity"
        / "Image Search"
        / "MyActivity.json"
    ).read_text()
)

GOOGLE_YOUTUBE_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR / "Portability" / "My Activity" / "YouTube" / "MyActivity.json"
    ).read_text()
)

GOOGLE_SHOPPING_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR
        / "Portability"
        / "My Activity"
        / "Shopping"
        / "MyActivity.json"
    ).read_text()
)

GOOGLE_DISCOVER_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR
        / "Portability"
        / "My Activity"
        / "Discover"
        / "MyActivity.json"
    ).read_text()
)

GOOGLE_LENS_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR
        / "Portability"
        / "My Activity"
        / "Google Lens"
        / "MyActivity.json"
    ).read_text()
)

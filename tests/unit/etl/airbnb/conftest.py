from __future__ import annotations

from context_use.testing.fixtures import load_fixture

_BASE = "users/alice/airbnb"

AIRBNB_MESSAGES_JSON: list[dict] = load_fixture(f"{_BASE}/v1/json/messages.json")
AIRBNB_SEARCH_HISTORY_JSON: list[dict] = load_fixture(
    f"{_BASE}/v1/json/search_history.json"
)
AIRBNB_REVIEWS_JSON: list[dict] = load_fixture(f"{_BASE}/v1/json/reviews.json")
AIRBNB_WISHLISTS_JSON: list[dict] = load_fixture(f"{_BASE}/v1/json/wishlists.json")
AIRBNB_RESERVATIONS_JSON: list[dict] = load_fixture(
    f"{_BASE}/v1/json/reservations.json"
)

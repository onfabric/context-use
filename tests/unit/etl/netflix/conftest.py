from __future__ import annotations

from pathlib import Path

_FIXTURES_ROOT = Path(__file__).parents[3] / "fixtures"
_BASE = "users/alice/netflix/v1"


def load_csv_fixture(relative_path: str) -> bytes:
    return (_FIXTURES_ROOT / relative_path).read_bytes()


VIEWING_ACTIVITY_CSV = load_csv_fixture(
    f"{_BASE}/CONTENT_INTERACTION/ViewingActivity.csv"
)
RATINGS_CSV = load_csv_fixture(f"{_BASE}/CONTENT_INTERACTION/Ratings.csv")
SEARCH_HISTORY_CSV = load_csv_fixture(f"{_BASE}/CONTENT_INTERACTION/SearchHistory.csv")
MY_LIST_CSV = load_csv_fixture(f"{_BASE}/CONTENT_INTERACTION/MyList.csv")
INDICATED_PREFERENCES_CSV = load_csv_fixture(
    f"{_BASE}/CONTENT_INTERACTION/IndicatedPreferences.csv"
)
MESSAGES_CSV = load_csv_fixture(f"{_BASE}/MESSAGES/MessagesSentByNetflix.csv")

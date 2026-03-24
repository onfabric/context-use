from __future__ import annotations

from pathlib import Path

_FIXTURES_ROOT = Path(__file__).parents[3] / "fixtures"
_BASE = "users/alice/bank/v1"


def load_csv_fixture(relative_path: str) -> bytes:
    return (_FIXTURES_ROOT / relative_path).read_bytes()


REVOLUT_CSV = load_csv_fixture(f"{_BASE}/revolut/account-statement.csv")
AMEX_CSV = load_csv_fixture(f"{_BASE}/amex/statement.csv")
BARCLAYS_CSV = load_csv_fixture(f"{_BASE}/barclays/statement.csv")

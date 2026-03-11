from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FIXTURES_ROOT = Path(__file__).parents[2] / "tests" / "fixtures"


def load_fixture(path: str) -> Any:
    """Load a JSON fixture file relative to tests/fixtures/."""
    return json.loads((_FIXTURES_ROOT / path).read_text())

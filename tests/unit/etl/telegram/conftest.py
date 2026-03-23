from __future__ import annotations

from typing import Any

from context_use.testing.fixtures import load_fixture

TELEGRAM_RESULT: dict[str, Any] = load_fixture(
    "users/alice/telegram/v1/threads/result.json"
)

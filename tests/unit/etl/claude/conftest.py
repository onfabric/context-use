from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parents[3] / "fixtures"
ALICE_CLAUDE_DIR = FIXTURES_DIR / "users" / "alice" / "claude" / "v1"

CLAUDE_CONVERSATIONS: list[dict] = json.loads(
    (ALICE_CLAUDE_DIR / "conversations.json").read_text()
)

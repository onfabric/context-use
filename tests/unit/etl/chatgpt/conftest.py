from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parents[3] / "fixtures"
ALICE_CHATGPT_DIR = FIXTURES_DIR / "users" / "alice" / "chatgpt" / "v1"

CHATGPT_CONVERSATIONS: list[dict] = json.loads(
    (ALICE_CHATGPT_DIR / "conversations.json").read_text()
)

from __future__ import annotations

from context_use.testing.fixtures import load_fixture

CLAUDE_CONVERSATIONS: list[dict] = load_fixture(
    "users/alice/claude/v1/threads/conversations.json"
)

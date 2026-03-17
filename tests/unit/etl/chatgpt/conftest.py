from __future__ import annotations

from context_use.testing.fixtures import load_fixture

CHATGPT_CONVERSATIONS: list[dict] = load_fixture(
    "users/alice/chatgpt/v1/threads/conversations.json"
)

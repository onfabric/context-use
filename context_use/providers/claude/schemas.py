from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

PROVIDER = "claude"


class ClaudeRole(StrEnum):
    HUMAN = "human"
    ASSISTANT = "assistant"


_EMIT_ROLES = frozenset(ClaudeRole)


class ClaudeContentBlock(BaseModel):
    type: str
    text: str | None = None


class ClaudeChatMessage(BaseModel):
    sender: str
    content: list[ClaudeContentBlock] = []
    created_at: str | None = None

    @property
    def is_emittable(self) -> bool:
        return self.sender in _EMIT_ROLES


class ClaudeConversation(BaseModel):
    chat_messages: list[ClaudeChatMessage]
    uuid: str | None = None
    name: str | None = None


class ClaudeConversationRecord(BaseModel):
    role: str
    content: str
    created_at: str | None = None
    conversation_id: str | None = None
    conversation_title: str | None = None
    source: str | None = None

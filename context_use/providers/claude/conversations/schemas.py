from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

PROVIDER = "claude"


class ClaudeRole(StrEnum):
    HUMAN = "human"
    ASSISTANT = "assistant"


class ClaudeContentBlock(BaseModel):
    type: str
    text: str | None = None


class ClaudeChatMessage(BaseModel):
    sender: str
    content: list[ClaudeContentBlock] = []
    created_at: str | None = None

    @property
    def is_emittable(self) -> bool:
        return self.sender in ClaudeRole


class ClaudeConversation(BaseModel):
    chat_messages: list[ClaudeChatMessage]
    uuid: str | None = None
    name: str | None = None

from __future__ import annotations

from pydantic import BaseModel

PROVIDER = "claude"


class ClaudeContentBlock(BaseModel):
    type: str
    text: str | None = None


class ClaudeChatMessage(BaseModel):
    sender: str
    content: list[ClaudeContentBlock] = []
    created_at: str | None = None


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

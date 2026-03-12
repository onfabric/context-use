from __future__ import annotations

from pydantic import BaseModel


class ClaudeConversationRecord(BaseModel):
    role: str
    content: str
    created_at: str | None = None
    conversation_id: str | None = None
    conversation_title: str | None = None
    source: str | None = None

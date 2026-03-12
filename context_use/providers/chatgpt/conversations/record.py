from __future__ import annotations

from pydantic import BaseModel


class ChatGPTConversationRecord(BaseModel):
    role: str
    content: str
    create_time: float | None = None
    conversation_id: str | None = None
    conversation_title: str | None = None
    source: str | None = None

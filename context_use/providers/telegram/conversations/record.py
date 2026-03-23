from __future__ import annotations

from pydantic import BaseModel


class TelegramConversationRecord(BaseModel):
    from_name: str | None
    from_id: str | None
    text: str
    date_unixtime: str
    chat_id: int
    chat_name: str | None
    chat_type: str
    is_self: bool
    source: str | None = None

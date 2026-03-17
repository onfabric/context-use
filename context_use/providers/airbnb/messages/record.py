from __future__ import annotations

from pydantic import BaseModel


class AirbnbMessageRecord(BaseModel):
    thread_id: int
    message_id: int
    created_at: str
    account_type: str
    account_id: int | None
    sender_platform: str | None
    content_type: str
    text: str
    source: str | None = None

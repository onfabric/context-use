from __future__ import annotations

from pydantic import BaseModel


class InstagramDirectMessageRecord(BaseModel):
    sender_name: str
    content: str | None
    link: str | None = None
    share_text: str | None = None
    original_content_owner: str | None = None
    timestamp_ms: int
    thread_path: str
    title: str
    source: str | None = None

from __future__ import annotations

from pydantic import BaseModel


class InstagramCommentRecord(BaseModel):
    comment: str
    media_owner: str | None = None
    timestamp: int
    source: str | None = None

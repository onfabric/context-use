from __future__ import annotations

from pydantic import BaseModel


class InstagramVideoWatchedRecord(BaseModel):
    author: str | None = None
    video_url: str | None = None
    timestamp: int
    source: str | None = None

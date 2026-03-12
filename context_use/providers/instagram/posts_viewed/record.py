from __future__ import annotations

from pydantic import BaseModel


class InstagramPostsViewedRecord(BaseModel):
    author: str | None = None
    post_url: str | None = None
    timestamp: int
    source: str | None = None

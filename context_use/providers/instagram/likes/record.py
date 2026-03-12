from __future__ import annotations

from pydantic import BaseModel


class InstagramLikedPostRecord(BaseModel):
    title: str
    href: str | None = None
    timestamp: int
    source: str | None = None

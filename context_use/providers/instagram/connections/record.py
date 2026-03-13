from __future__ import annotations

from pydantic import BaseModel


class InstagramConnectionRecord(BaseModel):
    username: str
    profile_url: str | None = None
    timestamp: int
    source: str | None = None

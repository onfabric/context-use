from __future__ import annotations

from pydantic import BaseModel


class InstagramProfileSearchRecord(BaseModel):
    username: str | None = None
    href: str | None = None
    timestamp: int
    source: str | None = None

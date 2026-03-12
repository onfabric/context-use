from __future__ import annotations

from pydantic import BaseModel


class InstagramMediaRecord(BaseModel):
    uri: str
    creation_timestamp: int
    title: str = ""
    source: str | None = None

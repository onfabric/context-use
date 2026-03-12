from __future__ import annotations

from pydantic import BaseModel


class InstagramSavedPostRecord(BaseModel):
    title: str
    href: str | None = None
    timestamp: int
    source: str | None = None


class InstagramSavedCollectionRecord(BaseModel):
    collection_name: str
    collection_created_at: int
    item_author: str
    item_href: str | None = None
    item_added_at: int
    source: str | None = None

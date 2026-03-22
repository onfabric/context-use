from __future__ import annotations

from pydantic import BaseModel


class InstagramAdsViewedRecord(BaseModel):
    author: str | None = None
    ad_url: str | None = None
    timestamp: int
    source: str | None = None

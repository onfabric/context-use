from __future__ import annotations

from pydantic import BaseModel


class NetflixSearchHistoryRecord(BaseModel):
    profile_name: str
    query_typed: str
    displayed_name: str
    utc_timestamp: str
    action: str
    device: str
    country_iso_code: str
    is_kids: str
    source: str | None = None

from __future__ import annotations

from pydantic import BaseModel


class NetflixMyListRecord(BaseModel):
    profile_name: str
    title_name: str
    utc_title_add_date: str
    country: str
    source: str | None = None

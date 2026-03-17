from __future__ import annotations

from pydantic import BaseModel


class NetflixRatingsRecord(BaseModel):
    profile_name: str
    title_name: str
    thumbs_value: str
    rating_type: str
    event_utc_ts: str
    device_model: str
    source: str | None = None

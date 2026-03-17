from __future__ import annotations

from pydantic import BaseModel


class NetflixViewingActivityRecord(BaseModel):
    profile_name: str
    title: str
    start_time: str
    duration: str
    country: str
    device_type: str
    bookmark: str
    attributes: str
    source: str | None = None

from __future__ import annotations

from pydantic import BaseModel


class NetflixIndicatedPreferencesRecord(BaseModel):
    profile_name: str
    show: str
    is_interested: str
    event_date: str
    has_watched: str
    source: str | None = None

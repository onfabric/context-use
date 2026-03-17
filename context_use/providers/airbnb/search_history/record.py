from __future__ import annotations

from pydantic import BaseModel


class AirbnbSearchRecord(BaseModel):
    city: str | None = None
    country: str | None = None
    state: str | None = None
    checkin_date: str | None = None
    checkout_date: str | None = None
    number_of_guests: int
    number_of_nights: int
    time_of_search: str
    raw_location: str | None = None
    source: str | None = None

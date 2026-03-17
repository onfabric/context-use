from __future__ import annotations

from pydantic import BaseModel


class AirbnbReservationRecord(BaseModel):
    confirmation_code: str
    hosting_url: str
    start_date: str
    nights: int
    number_of_guests: int
    number_of_adults: int
    number_of_children: int
    number_of_infants: int
    status: str
    created_at: str
    message: str | None = None
    source: str | None = None

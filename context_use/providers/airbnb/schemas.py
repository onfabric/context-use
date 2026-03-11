from __future__ import annotations

from pydantic import BaseModel

PROVIDER = "airbnb"


class AirbnbMessageRecord(BaseModel):
    """Flattened record for one message within a thread.

    Thread-level context (thread_id, owner_account_id) is injected
    during extraction so that ``transform()`` can determine direction
    and build the Collection without re-parsing the thread.
    """

    account_id: int | None = None
    account_type: str | None = None
    text: str
    created_at: str
    thread_id: int
    owner_account_id: int
    source: str | None = None


class AirbnbReservationRecord(BaseModel):
    confirmation_code: str
    hosting_url: str
    start_date: str
    nights: int
    number_of_guests: int
    status: str
    message: str | None = None
    created_at: str
    source: str | None = None


class AirbnbReviewRecord(BaseModel):
    comment: str
    rating: int
    submitted_at: str
    entity_id: int
    source: str | None = None


class AirbnbWishlistItemRecord(BaseModel):
    pdp_id: str
    wishlist_name: str
    wishlist_id: int
    check_in: str | None = None
    check_out: str | None = None
    source: str | None = None


class AirbnbSearchRecord(BaseModel):
    raw_location: str
    city: str | None = None
    country: str | None = None
    checkin_date: str | None = None
    checkout_date: str | None = None
    number_of_guests: int | None = None
    time_of_search: str
    source: str | None = None

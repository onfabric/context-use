from __future__ import annotations

from pydantic import BaseModel


class AirbnbWishlistItemRecord(BaseModel):
    wishlist_id: int
    wishlist_name: str
    item_id: int
    pdp_id: str
    pdp_type: str
    check_in: str | None = None
    check_out: str | None = None
    source: str | None = None

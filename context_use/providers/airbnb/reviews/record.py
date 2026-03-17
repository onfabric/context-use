from __future__ import annotations

from pydantic import BaseModel


class AirbnbReviewRecord(BaseModel):
    review_id: int
    reviewer_id: int
    comment: str
    rating: int
    entity_type: str
    entity_id: int
    bookable_id: int
    created_at: str
    comment_language: str
    source: str | None = None

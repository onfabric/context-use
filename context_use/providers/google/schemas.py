from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

PROVIDER = "google"


class GoogleActivityFileItem(BaseModel):
    header: str
    title: str
    time: datetime
    titleUrl: str | None = None
    products: list[str] | None = None
    activityControls: list[str] | None = None
    locationInfos: list[dict[str, object]] | None = None
    details: list[dict[str, object]] | None = None

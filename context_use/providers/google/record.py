from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GoogleRecord(BaseModel):
    title: str
    titleUrl: str | None = None
    time: datetime
    products: list[str] | None = None
    locationInfos: list[dict[str, object]] | None = None
    source: str | None = None

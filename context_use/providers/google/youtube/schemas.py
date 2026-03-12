from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GoogleYoutubeSubtitle(BaseModel):
    name: str
    url: str | None = None


class GoogleYoutubeFileItem(BaseModel):
    header: str
    title: str
    time: datetime
    titleUrl: str | None = None
    products: list[str] | None = None
    activityControls: list[str] | None = None
    details: list[dict] | None = None
    subtitles: list[GoogleYoutubeSubtitle] | None = None

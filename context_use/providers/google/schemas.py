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


class GoogleRecord(BaseModel):
    title: str
    titleUrl: str | None = None
    time: datetime
    products: list[str] | None = None
    locationInfos: list[dict[str, object]] | None = None
    source: str | None = None


class GoogleYoutubeRecord(GoogleRecord):
    subtitles: list[GoogleYoutubeSubtitle] | None = None

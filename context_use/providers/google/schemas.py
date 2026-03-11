from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

PROVIDER = "google"


class GoogleActivityFileItem(BaseModel):
    """File-level schema for a single item in a Google Takeout MyActivity.json array.

    Acts as a structural gate: if Google changes the export format in a way
    that removes or renames required fields, validation will fail and the
    pipe will skip the file.  Extra fields are tolerated (Pydantic default).
    """

    header: str
    title: str
    time: datetime
    titleUrl: str | None = None
    products: list[str] | None = None
    activityControls: list[str] | None = None
    locationInfos: list[dict] | None = None
    details: list[dict] | None = None
    subtitles: list[dict] | None = None


class GoogleYoutubeSubtitle(BaseModel):
    name: str
    url: str | None = None


class GoogleYoutubeFileItem(BaseModel):
    """File-level schema for a YouTube MyActivity.json item.

    Uses typed :class:`GoogleYoutubeSubtitle` entries so that structural
    changes to the subtitle/channel attribution format are caught.
    """

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
    locationInfos: list[dict] | None = None
    source: str | None = None


class GoogleYoutubeRecord(GoogleRecord):
    subtitles: list[dict] | None = None

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

PROVIDER = "google"


class GoogleRecord(BaseModel):
    """Base record for Google Takeout activity items.

    Maps the common fields present in every ``MyActivity.json`` entry
    across Google product directories (Search, Video Search, YouTube, etc.).
    """

    title: str
    titleUrl: str | None = None
    time: datetime
    products: list[str] | None = None
    locationInfos: list[dict] | None = None
    source: str | None = None


class GoogleYoutubeRecord(GoogleRecord):
    """Extended record for YouTube activity items.

    Adds ``subtitles`` which carries channel name / URL on
    ``Watched``, ``Liked``, ``Disliked``, and ``Saved`` entries.
    """

    subtitles: list[dict] | None = None

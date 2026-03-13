from __future__ import annotations

from context_use.providers.google.record import GoogleRecord
from context_use.providers.google.youtube.schemas import GoogleYoutubeSubtitle


class GoogleYoutubeRecord(GoogleRecord):
    subtitles: list[GoogleYoutubeSubtitle] | None = None

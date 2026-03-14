from __future__ import annotations

from context_use.providers.google.record import GoogleRecord
from context_use.providers.google.schemas import Subtitle


class GoogleYoutubeRecord(GoogleRecord):
    subtitles: list[Subtitle] | None = None

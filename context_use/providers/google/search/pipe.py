from __future__ import annotations

from context_use.batch.grouper import WindowGrouper
from context_use.etl.payload.models import (
    FibreSearch,
    FibreViewObject,
    Page,
    ThreadPayload,
)
from context_use.memories.config import MemoryConfig
from context_use.memories.prompt.search import GoogleSearchMemoryPromptBuilder
from context_use.providers.google.base import _BaseGooglePipe
from context_use.providers.google.record import GoogleRecord
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig

_SEARCH_PREFIXES = ("Searched for ", "Defined ")
_VIEW_PREFIXES = ("Visited ", "Viewed ")

_RECOGNISED_PREFIXES = _SEARCH_PREFIXES + _VIEW_PREFIXES


class _BaseGoogleSearchPipe(_BaseGooglePipe):
    _recognised_prefixes = _RECOGNISED_PREFIXES

    def _build_payload(self, record: GoogleRecord) -> ThreadPayload:
        url = self.clean_url(record.titleUrl)
        published = record.time

        # "Searched for ..." / "Defined ..." → FibreSearch
        for prefix in _SEARCH_PREFIXES:
            if record.title.startswith(prefix):
                name = record.title[len(prefix) :].strip() or None
                page = Page(name=name, url=url, published=published)  # type: ignore[reportCallIssue]
                return FibreSearch(object=page, published=published)  # type: ignore[reportCallIssue]

        # "Visited ..." / "Viewed ..." → FibreViewObject
        for prefix in _VIEW_PREFIXES:
            if record.title.startswith(prefix):
                name = record.title[len(prefix) :].strip() or None
                page = Page(name=name, url=url, published=published)  # type: ignore[reportCallIssue]
                return FibreViewObject(object=page, published=published)  # type: ignore[reportCallIssue]

        raise ValueError(f"Unrecognised title prefix: {record.title!r}")


class GoogleSearchPipe(_BaseGoogleSearchPipe):
    interaction_type = "google_search"
    archive_path_pattern = "Portability/My Activity/Search/MyActivity.json"


class GoogleVideoSearchPipe(_BaseGoogleSearchPipe):
    interaction_type = "google_video_search"
    archive_path_pattern = "Portability/My Activity/Video Search/MyActivity.json"


class GoogleImageSearchPipe(_BaseGoogleSearchPipe):
    interaction_type = "google_image_search"
    archive_path_pattern = "Portability/My Activity/Image Search/MyActivity.json"


SEARCH_MEMORY_CONFIG = MemoryConfig(
    prompt_builder=GoogleSearchMemoryPromptBuilder,
    grouper=WindowGrouper,
)

declare_interaction(
    InteractionConfig(pipe=GoogleSearchPipe, memory=SEARCH_MEMORY_CONFIG)
)
declare_interaction(
    InteractionConfig(pipe=GoogleVideoSearchPipe, memory=SEARCH_MEMORY_CONFIG)
)
declare_interaction(
    InteractionConfig(pipe=GoogleImageSearchPipe, memory=SEARCH_MEMORY_CONFIG)
)

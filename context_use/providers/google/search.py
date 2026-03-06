from __future__ import annotations

from collections.abc import Iterator

from context_use.etl.payload.models import (
    FibreSearch,
    FibreViewObject,
    Page,
    ThreadPayload,
)
from context_use.providers.google.base import _BaseGooglePipe
from context_use.providers.google.schemas import GoogleRecord
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

# ---------------------------------------------------------------------------
# Title-prefix constants
# ---------------------------------------------------------------------------

_SEARCH_PREFIXES = ("Searched for ", "Defined ")
_VIEW_PREFIXES = ("Visited ", "Viewed ")
_LENS_PREFIX = "Searched with Google Lens"

_RECOGNISED_PREFIXES = _SEARCH_PREFIXES + _VIEW_PREFIXES + (_LENS_PREFIX,)


# ---------------------------------------------------------------------------
# Shared search base
# ---------------------------------------------------------------------------


class _BaseGoogleSearchPipe(_BaseGooglePipe):
    """Shared logic for Google search-family pipes.

    Overrides :meth:`extract_file` to filter out records with
    unrecognised title prefixes, and provides :meth:`_build_payload`
    that dispatches by prefix to :class:`FibreSearch` or
    :class:`FibreViewObject`.

    Concrete subclasses set ``interaction_type`` and
    ``archive_path_pattern`` only.
    """

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[GoogleRecord]:
        for record in super().extract_file(source_uri, storage):
            if any(record.title.startswith(p) for p in _RECOGNISED_PREFIXES):
                yield record

    def _build_payload(self, record: GoogleRecord) -> ThreadPayload:
        url = self.clean_url(record.titleUrl)
        published = record.time

        # --- Lens: title IS the prefix (no additional content) ---
        if record.title.startswith(_LENS_PREFIX):
            page = Page(url=url, published=published)  # type: ignore[reportCallIssue]
            return FibreSearch(object=page, published=published)  # type: ignore[reportCallIssue]

        # --- "Searched for ..." / "Defined ..." → FibreSearch ---
        for prefix in _SEARCH_PREFIXES:
            if record.title.startswith(prefix):
                name = record.title[len(prefix) :].strip() or None
                page = Page(name=name, url=url, published=published)  # type: ignore[reportCallIssue]
                return FibreSearch(object=page, published=published)  # type: ignore[reportCallIssue]

        # --- "Visited ..." / "Viewed ..." → FibreViewObject ---
        for prefix in _VIEW_PREFIXES:
            if record.title.startswith(prefix):
                name = record.title[len(prefix) :].strip() or None
                page = Page(name=name, url=url, published=published)  # type: ignore[reportCallIssue]
                return FibreViewObject(object=page, published=published)  # type: ignore[reportCallIssue]

        raise ValueError(f"Unrecognised title prefix: {record.title!r}")


# ---------------------------------------------------------------------------
# Concrete search pipes
# ---------------------------------------------------------------------------


class GoogleSearchPipe(_BaseGoogleSearchPipe):
    """Google Search activity."""

    interaction_type = "google_search"
    archive_path_pattern = "Portability/My Activity/Search/MyActivity.json"


class GoogleVideoSearchPipe(_BaseGoogleSearchPipe):
    """Google Video Search activity."""

    interaction_type = "google_video_search"
    archive_path_pattern = "Portability/My Activity/Video Search/MyActivity.json"


class GoogleImageSearchPipe(_BaseGoogleSearchPipe):
    """Google Image Search activity."""

    interaction_type = "google_image_search"
    archive_path_pattern = "Portability/My Activity/Image Search/MyActivity.json"


class GoogleLensPipe(_BaseGoogleSearchPipe):
    """Google Lens activity."""

    interaction_type = "google_lens"
    archive_path_pattern = "Portability/My Activity/Google Lens/MyActivity.json"


class GoogleDiscoverPipe(_BaseGoogleSearchPipe):
    """Google Discover activity."""

    interaction_type = "google_discover"
    archive_path_pattern = "Portability/My Activity/Discover/MyActivity.json"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

declare_interaction(InteractionConfig(pipe=GoogleSearchPipe, memory=None))
declare_interaction(InteractionConfig(pipe=GoogleVideoSearchPipe, memory=None))
declare_interaction(InteractionConfig(pipe=GoogleImageSearchPipe, memory=None))
declare_interaction(InteractionConfig(pipe=GoogleLensPipe, memory=None))
declare_interaction(InteractionConfig(pipe=GoogleDiscoverPipe, memory=None))

from __future__ import annotations

from datetime import datetime

from context_use.etl.payload.models import (
    FibreAddObjectToCollection,
    FibreCollectionFavourites,
    FibreDislike,
    FibreFollowing,
    FibreLike,
    FibreSearch,
    FibreViewObject,
    Page,
    Person,
    Profile,
    ThreadPayload,
    Video,
)
from context_use.providers.google.base import _BaseGooglePipe
from context_use.providers.google.search.pipe import SEARCH_MEMORY_CONFIG
from context_use.providers.google.youtube.record import GoogleYoutubeRecord
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig

_SEARCH_PREFIXES = ("Searched for ",)
_VIEW_PREFIXES = ("Watched ", "Viewed ")
_LIKE_PREFIXES = ("Liked ",)
_DISLIKE_PREFIXES = ("Disliked ",)
_SUBSCRIBE_PREFIXES = ("Subscribed to ",)
_SAVE_PREFIXES = ("Saved ",)

_RECOGNISED_PREFIXES = (
    _SEARCH_PREFIXES
    + _VIEW_PREFIXES
    + _LIKE_PREFIXES
    + _DISLIKE_PREFIXES
    + _SUBSCRIBE_PREFIXES
    + _SAVE_PREFIXES
)


class GoogleYoutubePipe(_BaseGooglePipe):
    interaction_type = "google_youtube"
    archive_path_pattern = "Portability/My Activity/YouTube/MyActivity.json"
    record_schema = GoogleYoutubeRecord  # type: ignore[assignment]
    _recognised_prefixes = _RECOGNISED_PREFIXES

    def _build_payload(  # type: ignore[override]
        self,
        record: GoogleYoutubeRecord,
    ) -> ThreadPayload:
        url = self.clean_url(record.titleUrl)
        published = record.time
        channel = _extract_channel(record)

        # "Searched for ..." → FibreSearch
        for prefix in _SEARCH_PREFIXES:
            if record.title.startswith(prefix):
                name = record.title[len(prefix) :].strip() or None
                page = Page(name=name, url=url, published=published)  # type: ignore[reportCallIssue]
                return FibreSearch(object=page, published=published)  # type: ignore[reportCallIssue]

        # "Watched ..." / "Viewed ..." → FibreViewObject
        for prefix in _VIEW_PREFIXES:
            if record.title.startswith(prefix):
                name = record.title[len(prefix) :].strip() or None
                video = _make_video(name, url, published, channel)
                return FibreViewObject(object=video, published=published)  # type: ignore[reportCallIssue]

        # "Liked ..." → FibreLike
        for prefix in _LIKE_PREFIXES:
            if record.title.startswith(prefix):
                name = record.title[len(prefix) :].strip() or None
                video = _make_video(name, url, published, channel)
                return FibreLike(object=video, published=published)  # type: ignore[reportCallIssue]

        # "Disliked ..." → FibreDislike
        for prefix in _DISLIKE_PREFIXES:
            if record.title.startswith(prefix):
                name = record.title[len(prefix) :].strip() or None
                video = _make_video(name, url, published, channel)
                return FibreDislike(object=video, published=published)  # type: ignore[reportCallIssue]

        # "Subscribed to ..." → FibreFollowing
        for prefix in _SUBSCRIBE_PREFIXES:
            if record.title.startswith(prefix):
                name = record.title[len(prefix) :].strip() or None
                profile = Profile(name=name, url=url, published=published)  # type: ignore[reportCallIssue]
                return FibreFollowing(object=profile, published=published)  # type: ignore[reportCallIssue]

        # "Saved ..." → FibreAddObjectToCollection
        for prefix in _SAVE_PREFIXES:
            if record.title.startswith(prefix):
                name = record.title[len(prefix) :].strip() or None
                video = _make_video(name, url, published, channel)
                return FibreAddObjectToCollection(  # type: ignore[reportCallIssue]
                    object=video,
                    target=FibreCollectionFavourites(),  # type: ignore[reportCallIssue]
                    published=published,
                )

        raise ValueError(f"Unrecognised title prefix: {record.title!r}")


def _extract_channel(record: GoogleYoutubeRecord) -> Person | None:
    if not record.subtitles:
        return None
    for entry in record.subtitles:
        if entry.name and entry.url:
            return Person(name=entry.name, url=entry.url)  # type: ignore[reportCallIssue]
        if entry.name:
            return Person(name=entry.name)  # type: ignore[reportCallIssue]
    return None


def _make_video(
    name: str | None,
    url: str | None,
    published: datetime,
    channel: Person | None,
) -> Video:
    kwargs: dict[str, object] = {}
    if name:
        kwargs["name"] = name
    if url:
        kwargs["url"] = url
    kwargs["published"] = published
    if channel:
        kwargs["attributedTo"] = channel
    return Video(**kwargs)  # type: ignore[reportCallIssue]


declare_interaction(
    InteractionConfig(pipe=GoogleYoutubePipe, memory=SEARCH_MEMORY_CONFIG)
)

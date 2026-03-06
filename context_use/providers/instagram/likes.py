from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreLike,
    FibrePost,
    Profile,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.schemas import (
    InstagramHrefTimestampSchema,
    InstagramLabelValue,
    InstagramLikedPostRecord,
    InstagramStringListDataWrapper,
)
from context_use.providers.registry import register_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)

_LikeItem = InstagramStringListDataWrapper[InstagramHrefTimestampSchema]


class _InstagramLikePipe(Pipe[InstagramLikedPostRecord]):
    """Shared transform logic for Instagram like pipes.

    Subclasses implement :meth:`extract_file` to parse their specific
    archive format; :meth:`transform` is inherited.
    """

    provider = "instagram"
    record_schema = InstagramLikedPostRecord

    def transform(
        self,
        record: InstagramLikedPostRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)

        post_kwargs: dict = {}
        if record.href:
            post_kwargs["url"] = record.href
        if record.title:
            post_kwargs["attributedTo"] = Profile(  # type: ignore[reportCallIssue]
                name=record.title,
            )

        post = FibrePost(**post_kwargs)  # type: ignore[reportCallIssue]

        payload = FibreLike(  # type: ignore[reportCallIssue]
            object=post,
            published=published,
        )

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview(task.provider) or "",
            payload=payload.to_dict(),
            source=record.source,
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=published,
        )


# ---------------------------------------------------------------------------
# V0 pipes — string_list_data format (top-level wrapper key)
# ---------------------------------------------------------------------------


class InstagramLikedPostsV0Pipe(_InstagramLikePipe):
    """ETL pipe for Instagram liked posts — v0 archive format.

    Reads ``likes_media_likes`` from
    ``your_instagram_activity/likes/liked_posts.json``.
    Each item has ``{title, string_list_data: [{href, value, timestamp}]}``.
    Creates ``FibreLike(object=FibrePost(...))``.
    """

    interaction_type = "instagram_liked_posts"
    archive_version = 0
    archive_path_pattern = "your_instagram_activity/likes/liked_posts.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramLikedPostRecord]:
        raw = storage.read(source_uri)
        data = json.loads(raw)
        items = data.get("likes_media_likes", [])
        for raw_item in items:
            title = raw_item.get("title", "")
            parsed = _LikeItem.model_validate(raw_item)
            for entry in parsed.string_list_data:
                yield InstagramLikedPostRecord(
                    title=title,
                    href=entry.href,
                    timestamp=entry.timestamp,
                    source=json.dumps(raw_item),
                )


class InstagramStoryLikesV0Pipe(_InstagramLikePipe):
    """ETL pipe for Instagram story likes — v0 archive format.

    Reads ``story_activities_story_likes`` from
    ``your_instagram_activity/story_interactions/story_likes.json``.
    Each item has ``{title, string_list_data: [{timestamp}]}``.
    Creates ``FibreLike(object=FibrePost(attributedTo=Profile(...)))``.
    """

    interaction_type = "instagram_story_likes"
    archive_version = 0
    archive_path_pattern = "your_instagram_activity/story_interactions/story_likes.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramLikedPostRecord]:
        raw = storage.read(source_uri)
        data = json.loads(raw)
        items = data.get("story_activities_story_likes", [])
        for raw_item in items:
            title = raw_item.get("title", "")
            parsed = _LikeItem.model_validate(raw_item)
            for entry in parsed.string_list_data:
                yield InstagramLikedPostRecord(
                    title=title,
                    href=entry.href,
                    timestamp=entry.timestamp,
                    source=json.dumps(raw_item),
                )


# ---------------------------------------------------------------------------
# V1 pipes — label_values format (bare JSON array)
# ---------------------------------------------------------------------------


class InstagramLikedPostsPipe(_InstagramLikePipe):
    """ETL pipe for Instagram liked posts — v1 archive format.

    V1 files are a bare JSON array of ``{timestamp, media, label_values}``
    items.  The post URL is in ``label_values`` with ``label == "URL"``,
    and the author username is nested inside an ``Owner`` dict entry.
    Creates ``FibreLike(object=FibrePost(...))``.
    """

    interaction_type = "instagram_liked_posts"
    archive_version = 1
    archive_path_pattern = "your_instagram_activity/likes/liked_posts.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramLikedPostRecord]:
        raw = storage.read(source_uri)
        items: list[dict] = json.loads(raw)
        for raw_item in items:
            timestamp = raw_item.get("timestamp")
            if timestamp is None:
                continue

            href: str | None = None
            title: str | None = None

            for lv_data in raw_item.get("label_values", []):
                # Simple label_value entries have "label"
                if "label" in lv_data:
                    lv = InstagramLabelValue.model_validate(lv_data)
                    if lv.label == "URL":
                        href = lv.href or lv.value

                # Nested Owner dict: {title: "Owner", dict: [{dict: [...]}]}
                if lv_data.get("title") == "Owner":
                    title = self._extract_owner_username(lv_data)

            yield InstagramLikedPostRecord(
                title=title or "",
                href=href,
                timestamp=timestamp,
                source=json.dumps(raw_item),
            )

    @staticmethod
    def _extract_owner_username(owner_data: dict) -> str | None:
        """Extract the username from the nested Owner dict structure.

        The Owner entry looks like::

            {
                "title": "Owner",
                "dict": [
                    {
                        "title": "",
                        "dict": [
                            {"label": "Username", "value": "some_user"},
                            {"label": "Name", "value": "Some User"},
                            ...
                        ]
                    }
                ]
            }
        """
        for outer in owner_data.get("dict", []):
            for inner in outer.get("dict", []):
                if inner.get("label") == "Username":
                    return inner.get("value")
        return None


class InstagramStoryLikesPipe(_InstagramLikePipe):
    """ETL pipe for Instagram story likes — v1 archive format.

    V1 files are a bare JSON array of ``{timestamp, media, label_values}``
    items.  The story author username is nested inside an ``Owner`` dict entry.
    Creates ``FibreLike(object=FibrePost(attributedTo=Profile(...)))``.
    """

    interaction_type = "instagram_story_likes"
    archive_version = 1
    archive_path_pattern = "your_instagram_activity/story_interactions/story_likes.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramLikedPostRecord]:
        raw = storage.read(source_uri)
        items: list[dict] = json.loads(raw)
        for raw_item in items:
            timestamp = raw_item.get("timestamp")
            if timestamp is None:
                continue

            href: str | None = None
            title: str | None = None

            for lv_data in raw_item.get("label_values", []):
                if "label" in lv_data:
                    lv = InstagramLabelValue.model_validate(lv_data)
                    if lv.label == "URL":
                        href = lv.href or lv.value

                if lv_data.get("title") == "Owner":
                    title = self._extract_owner_username(lv_data)

            yield InstagramLikedPostRecord(
                title=title or "",
                href=href,
                timestamp=timestamp,
                source=json.dumps(raw_item),
            )

    @staticmethod
    def _extract_owner_username(owner_data: dict) -> str | None:
        """Extract the username from the nested Owner dict structure."""
        for outer in owner_data.get("dict", []):
            for inner in outer.get("dict", []):
                if inner.get("label") == "Username":
                    return inner.get("value")
        return None


register_interaction(InteractionConfig(pipe=InstagramLikedPostsV0Pipe, memory=None))
register_interaction(InteractionConfig(pipe=InstagramLikedPostsPipe, memory=None))
register_interaction(InteractionConfig(pipe=InstagramStoryLikesV0Pipe, memory=None))
register_interaction(InteractionConfig(pipe=InstagramStoryLikesPipe, memory=None))

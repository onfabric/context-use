from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import ijson

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreLike,
    FibrePost,
    Profile,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.likes.record import InstagramLikedPostRecord
from context_use.providers.instagram.likes.schemas import (
    InstagramLikedPostsV0Manifest,
)
from context_use.providers.instagram.likes.story_likes_schemas import (
    Model as StoryLikesV0Manifest,
)
from context_use.providers.instagram.schemas import (
    PROVIDER,
    InstagramLabelValue,
    InstagramV1ActivityItem,
    InstagramV1OwnerEntry,
    _fix_strings_recursive,
    extract_owner_username,
)
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class _InstagramLikePipe(Pipe[InstagramLikedPostRecord]):
    """Shared transform logic for Instagram like pipes.

    Subclasses implement :meth:`extract_file` to parse their specific
    archive format; :meth:`transform` is inherited.
    """

    provider = PROVIDER
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
        manifest = InstagramLikedPostsV0Manifest.model_validate_json(raw)
        for item in manifest.likes_media_likes:
            for entry in item.string_list_data:
                yield InstagramLikedPostRecord(
                    title=item.title,
                    href=entry.href,
                    timestamp=entry.timestamp,
                    source=item.model_dump_json(),
                )


class InstagramStoryLikesV0Pipe(_InstagramLikePipe):
    interaction_type = "instagram_story_likes"
    archive_version = 0
    archive_path_pattern = "your_instagram_activity/story_interactions/story_likes.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramLikedPostRecord]:
        raw = storage.read(source_uri)
        fixed = _fix_strings_recursive(json.loads(raw))
        manifest = StoryLikesV0Manifest.model_validate(fixed)
        for item in manifest.story_activities_story_likes:
            for entry in item.string_list_data:
                yield InstagramLikedPostRecord(
                    title=item.title,
                    href=None,
                    timestamp=entry.timestamp,
                    source=item.model_dump_json(),
                )


def _extract_like_item(item: InstagramV1ActivityItem) -> InstagramLikedPostRecord:
    href: str | None = None
    title: str | None = None
    for lv in item.label_values:
        if isinstance(lv, InstagramLabelValue):
            if lv.label == "URL":
                href = lv.href or lv.value
        elif isinstance(lv, InstagramV1OwnerEntry) and lv.title == "Owner":
            title = extract_owner_username(lv)
    return InstagramLikedPostRecord(
        title=title or "",
        href=href,
        timestamp=item.timestamp,
        source=item.model_dump_json(),
    )


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
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                yield _extract_like_item(InstagramV1ActivityItem.model_validate(raw))
        finally:
            stream.close()


class InstagramStoryLikesPipe(_InstagramLikePipe):
    interaction_type = "instagram_story_likes"
    archive_version = 1
    archive_path_pattern = "your_instagram_activity/story_interactions/story_likes.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramLikedPostRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                yield _extract_like_item(InstagramV1ActivityItem.model_validate(raw))
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=InstagramLikedPostsPipe, memory=None))
declare_interaction(InteractionConfig(pipe=InstagramStoryLikesPipe, memory=None))

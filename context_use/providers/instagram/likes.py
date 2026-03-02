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
    InstagramLikedPostRecord,
    InstagramStringListDataWrapper,
)
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
    archive_version = 1
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


class InstagramLikedPostsPipe(_InstagramLikePipe):
    """ETL pipe for Instagram liked posts.

    Reads ``likes_media_likes`` from
    ``your_instagram_activity/likes/liked_posts.json``.
    Each item has ``{title, string_list_data: [{href, value, timestamp}]}``.
    Creates ``FibreLike(object=FibrePost(...))``.
    """

    interaction_type = "instagram_liked_posts"
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


class InstagramStoryLikesPipe(_InstagramLikePipe):
    """ETL pipe for Instagram story likes.

    Reads ``story_activities_story_likes`` from
    ``your_instagram_activity/story_interactions/story_likes.json``.
    Each item has ``{title, string_list_data: [{timestamp}]}``.
    Creates ``FibreLike(object=FibrePost(attributedTo=Profile(...)))``.
    """

    interaction_type = "instagram_story_likes"
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


LIKED_POSTS_CONFIG = InteractionConfig(
    pipe=InstagramLikedPostsPipe,
    memory=None,
)

STORY_LIKES_CONFIG = InteractionConfig(
    pipe=InstagramStoryLikesPipe,
    memory=None,
)

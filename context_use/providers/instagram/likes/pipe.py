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
from context_use.providers.instagram.likes.schema_liked_posts import (
    Model as LikedPostsManifest,
)
from context_use.providers.instagram.likes.schema_story_likes import (
    Model as StoryLikesManifest,
)
from context_use.providers.instagram.schemas import Model as ActivityItem
from context_use.providers.instagram.utils import (
    PROVIDER,
    extract_owner_username,
    fix_strings_recursive,
)
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class _InstagramLikePipe(Pipe[InstagramLikedPostRecord]):
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
    interaction_type = "instagram_liked_posts"
    archive_version = 0
    archive_path_pattern = "your_instagram_activity/likes/liked_posts.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramLikedPostRecord]:
        raw = storage.read(source_uri)
        data = fix_strings_recursive(json.loads(raw))
        manifest = LikedPostsManifest.model_validate(data)
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
        data = fix_strings_recursive(json.loads(raw))
        manifest = StoryLikesManifest.model_validate(data)
        for item in manifest.story_activities_story_likes:
            for entry in item.string_list_data:
                yield InstagramLikedPostRecord(
                    title=item.title,
                    href=None,
                    timestamp=entry.timestamp,
                    source=item.model_dump_json(),
                )


def _extract_like_item(item: ActivityItem) -> InstagramLikedPostRecord:
    href: str | None = None
    title: str | None = None
    for lv in item.label_values:
        if lv.label == "URL":
            href = lv.href or lv.value
        else:
            owner = extract_owner_username(lv)
            if owner:
                title = owner
    return InstagramLikedPostRecord(
        title=title or "",
        href=href,
        timestamp=item.timestamp,
        source=item.model_dump_json(),
    )


class InstagramLikedPostsPipe(_InstagramLikePipe):
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
                yield _extract_like_item(
                    ActivityItem.model_validate(fix_strings_recursive(raw))
                )
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=InstagramLikedPostsPipe, memory=None))
declare_interaction(InteractionConfig(pipe=InstagramStoryLikesV0Pipe, memory=None))

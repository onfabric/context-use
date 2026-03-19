from __future__ import annotations

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
from context_use.providers.instagram.schemas import PROVIDER
from context_use.providers.instagram.story_likes.record import InstagramStoryLikeRecord
from context_use.providers.instagram.story_likes.schemas import (
    InstagramStoryLikesV0Manifest,
)
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class _InstagramStoryLikePipe(Pipe[InstagramStoryLikeRecord]):
    provider = PROVIDER
    record_schema = InstagramStoryLikeRecord
    interaction_type = "instagram_story_likes"

    def transform(
        self,
        record: InstagramStoryLikeRecord,
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


class InstagramStoryLikesV0Pipe(_InstagramStoryLikePipe):
    archive_version = 0
    archive_path_pattern = "your_instagram_activity/story_interactions/story_likes.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramStoryLikeRecord]:
        raw = storage.read(source_uri)
        manifest = InstagramStoryLikesV0Manifest.model_validate_json(raw)
        for item in manifest.story_activities_story_likes:
            for entry in item.string_list_data:
                yield InstagramStoryLikeRecord(
                    title=item.title,
                    href=entry.href,
                    timestamp=entry.timestamp,
                    source=item.model_dump_json(),
                )


declare_interaction(InteractionConfig(pipe=InstagramStoryLikesV0Pipe, memory=None))

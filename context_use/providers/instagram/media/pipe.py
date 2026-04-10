from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import ijson

from context_use.batch.grouper import WindowGrouper
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreCreateObject,
    Image,
    Video,
)
from context_use.memories.config import MemoryConfig
from context_use.memories.prompt.media import MediaMemoryPromptBuilder
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.media.record import InstagramMediaRecord
from context_use.providers.instagram.media.schemas import (
    InstagramMediaItem,
    InstagramPostsEntry,
    InstagramReelsManifest,
    InstagramStoriesManifest,
)
from context_use.providers.instagram.schemas import PROVIDER
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)

_VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".webm", ".srt")


def _items_to_records(
    items: list[InstagramMediaItem],
) -> Iterator[InstagramMediaRecord]:
    for item in items:
        yield InstagramMediaRecord(
            uri=item.uri,
            creation_timestamp=item.creation_timestamp,
            title=item.title,
            source=item.model_dump_json(),
        )


class _InstagramMediaPipe(Pipe[InstagramMediaRecord]):
    provider = PROVIDER
    archive_version = 1
    record_schema = InstagramMediaRecord

    def transform(
        self,
        record: InstagramMediaRecord,
        task: EtlTask,
    ) -> ThreadRow:
        payload = self._build_payload(record)
        assert payload is not None, f"Unexpected None payload for uri={record.uri!r}"

        asat = datetime.fromtimestamp(float(record.creation_timestamp), tz=UTC)

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview(task.provider) or "",
            payload=payload.to_dict(),
            source=record.source,
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=asat,
            asset_uri=(f"{task.archive_id}/{record.uri}" if record.uri else None),
        )

    @staticmethod
    def _build_payload(record: InstagramMediaRecord) -> FibreCreateObject:
        published = datetime.fromtimestamp(float(record.creation_timestamp), tz=UTC)

        is_video = record.uri.lower().endswith(_VIDEO_EXTENSIONS)
        if is_video:
            media_obj = Video(name=record.title or None, published=published)  # type: ignore[reportCallIssue]
        else:
            media_obj = Image(name=record.title or None, published=published)  # type: ignore[reportCallIssue]

        return FibreCreateObject(  # type: ignore[reportCallIssue]
            object=media_obj,
            published=published,
        )


class InstagramStoriesPipe(_InstagramMediaPipe):
    interaction_type = "instagram_stories"
    archive_path_pattern = "your_instagram_activity/media/stories.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramMediaRecord]:
        raw = storage.read(source_uri)
        manifest = InstagramStoriesManifest.model_validate_json(raw)
        yield from _items_to_records(manifest.ig_stories)


class InstagramReelsPipe(_InstagramMediaPipe):
    interaction_type = "instagram_reels"
    archive_path_pattern = "your_instagram_activity/media/reels.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramMediaRecord]:
        raw = storage.read(source_uri)
        manifest = InstagramReelsManifest.model_validate_json(raw)

        all_items: list[InstagramMediaItem] = []
        for entry in manifest.ig_reels_media:
            all_items.extend(entry.media)

        yield from _items_to_records(all_items)


class InstagramPostsPipe(_InstagramMediaPipe):
    interaction_type = "instagram_posts"
    archive_path_pattern = "your_instagram_activity/media/posts_*.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramMediaRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                entry = InstagramPostsEntry.model_validate(raw)
                yield from _items_to_records(entry.media)
        finally:
            stream.close()


_MEDIA_MEMORY_CONFIG = MemoryConfig(
    prompt_builder=MediaMemoryPromptBuilder,
    grouper=WindowGrouper,
)

declare_interaction(
    InteractionConfig(
        pipe=InstagramStoriesPipe,
        memory=_MEDIA_MEMORY_CONFIG,
        asset_description=True,
    )
)
declare_interaction(
    InteractionConfig(
        pipe=InstagramReelsPipe,
        memory=_MEDIA_MEMORY_CONFIG,
        asset_description=True,
    )
)
declare_interaction(
    InteractionConfig(
        pipe=InstagramPostsPipe,
        memory=_MEDIA_MEMORY_CONFIG,
        asset_description=True,
    )
)

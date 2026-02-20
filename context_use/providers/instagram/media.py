from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

from context_use.batch.grouper import WindowGrouper
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.models.etl_task import EtlTask
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreCreateObject,
    Image,
    Video,
)
from context_use.memories.config import MemoryConfig
from context_use.memories.prompt.media import MediaMemoryPromptBuilder
from context_use.providers.instagram.schemas import (
    InstagramMediaItem,
    InstagramMediaRecord,
    InstagramReelsManifest,
    InstagramStoriesManifest,
)
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def _infer_media_type(uri: str) -> str:
    """Infer 'Image' or 'Video' from file extension."""
    lower = uri.lower()
    if lower.endswith((".mp4", ".mov", ".avi", ".webm", ".srt")):
        return "Video"
    return "Image"


def _items_to_records(
    items: list[InstagramMediaItem],
    source_file: str,
) -> Iterator[InstagramMediaRecord]:
    """Convert InstagramMediaItems into InstagramMediaRecord instances."""
    for item in items:
        yield InstagramMediaRecord(
            uri=item.uri,
            creation_timestamp=item.creation_timestamp,
            title=item.title,
            media_type=_infer_media_type(item.uri),
            source=json.dumps({"file": source_file, "uri": item.uri}),
        )


class _InstagramMediaPipe(Pipe[InstagramMediaRecord]):
    """Shared transform logic for Instagram media (stories and reels).

    Subclasses implement :meth:`extract` to parse their specific
    manifest format; :meth:`transform` is inherited.
    """

    provider = "instagram"
    archive_version = "v1"
    record_schema = InstagramMediaRecord

    def transform(
        self,
        record: InstagramMediaRecord,
        task: EtlTask,
    ) -> ThreadRow:
        payload = self._build_payload(record, task.provider)
        assert payload is not None, f"Unexpected None payload for uri={record.uri!r}"

        asat = datetime.fromtimestamp(float(record.creation_timestamp), tz=UTC)
        unique_key = f"{task.interaction_type}:{payload.unique_key_suffix()}"

        return ThreadRow(
            unique_key=unique_key,
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
    def _build_payload(
        record: InstagramMediaRecord,
        provider: str,
    ) -> FibreCreateObject | None:
        published = datetime.fromtimestamp(float(record.creation_timestamp), tz=UTC)

        if record.media_type == "Video":
            media_obj = Video(
                url=record.uri, name=record.title or None, published=published
            )  # type: ignore[reportCallIssue]
        else:
            media_obj = Image(
                url=record.uri, name=record.title or None, published=published
            )  # type: ignore[reportCallIssue]

        return FibreCreateObject(  # type: ignore[reportCallIssue]
            object=media_obj,
            published=published,
        )


class InstagramStoriesPipe(_InstagramMediaPipe):
    """ETL pipe for Instagram stories.

    Reads ``stories.json``, yields individual
    :class:`InstagramMediaRecord` instances, and transforms each
    into a :class:`ThreadRow` with an ActivityStreams payload.
    """

    interaction_type = "instagram_stories"
    archive_path_pattern = "your_instagram_activity/media/stories.json"

    def extract(
        self,
        task: EtlTask,
        storage: StorageBackend,
    ) -> Iterator[InstagramMediaRecord]:
        raw = storage.read(task.source_uri)
        manifest = InstagramStoriesManifest.model_validate_json(raw)
        yield from _items_to_records(manifest.ig_stories, task.source_uri)


class InstagramReelsPipe(_InstagramMediaPipe):
    """ETL pipe for Instagram reels.

    Reads ``reels.json``, flattens nested media lists, yields individual
    :class:`InstagramMediaRecord` instances, and transforms each
    into a :class:`ThreadRow` with an ActivityStreams payload.
    """

    interaction_type = "instagram_reels"
    archive_path_pattern = "your_instagram_activity/media/reels.json"

    def extract(
        self,
        task: EtlTask,
        storage: StorageBackend,
    ) -> Iterator[InstagramMediaRecord]:
        raw = storage.read(task.source_uri)
        manifest = InstagramReelsManifest.model_validate_json(raw)

        all_items: list[InstagramMediaItem] = []
        for entry in manifest.ig_reels_media:
            all_items.extend(entry.media)

        yield from _items_to_records(all_items, task.source_uri)


_MEDIA_MEMORY_CONFIG = MemoryConfig(
    prompt_builder=MediaMemoryPromptBuilder,
    grouper=WindowGrouper,
)

STORIES_CONFIG = InteractionConfig(
    pipe=InstagramStoriesPipe,
    memory=_MEDIA_MEMORY_CONFIG,
)

REELS_CONFIG = InteractionConfig(
    pipe=InstagramReelsPipe,
    memory=_MEDIA_MEMORY_CONFIG,
)

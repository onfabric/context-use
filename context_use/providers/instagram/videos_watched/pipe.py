from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import ijson

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreViewObject,
    Profile,
    Video,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.schemas import (
    PROVIDER,
    InstagramLabelValue,
    InstagramV1ActivityItem,
)
from context_use.providers.instagram.videos_watched.record import (
    InstagramVideoWatchedRecord,
)
from context_use.providers.instagram.videos_watched.schemas import (
    InstagramVideosWatchedV0Manifest,
)
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class _InstagramVideosWatchedPipe(Pipe[InstagramVideoWatchedRecord]):
    """Shared transform logic for Instagram videos watched (v0 and v1).

    Subclasses implement :meth:`extract_file` to parse their specific
    archive format; :meth:`transform` is inherited.
    """

    provider = PROVIDER
    interaction_type = "instagram_videos_watched"
    record_schema = InstagramVideoWatchedRecord

    def transform(
        self,
        record: InstagramVideoWatchedRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)

        # Build the Video object — author becomes attributedTo Profile
        video_kwargs: dict = {}
        if record.video_url:
            video_kwargs["url"] = record.video_url
        if record.author:
            video_kwargs["attributedTo"] = Profile(  # type: ignore[reportCallIssue]
                name=record.author,
                url=f"https://www.instagram.com/{record.author}",
            )

        video = Video(**video_kwargs)  # type: ignore[reportCallIssue]

        payload = FibreViewObject(  # type: ignore[reportCallIssue]
            object=video,
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


class InstagramVideosWatchedV0Pipe(_InstagramVideosWatchedPipe):
    """ETL pipe for Instagram videos watched — v0 archive format.

    V0 files contain a top-level ``impressions_history_videos_watched``
    key wrapping an array of ``{string_map_data: {Author, Time}}`` items.
    """

    archive_version = 0
    archive_path_pattern = "ads_information/ads_and_topics/videos_watched.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramVideoWatchedRecord]:
        raw = storage.read(source_uri)
        manifest = InstagramVideosWatchedV0Manifest.model_validate_json(raw)
        for item in manifest.impressions_history_videos_watched:
            yield InstagramVideoWatchedRecord(
                author=item.string_map_data.Author.value,
                timestamp=item.string_map_data.Time.timestamp,
                source=item.model_dump_json(),
            )


class InstagramVideosWatchedPipe(_InstagramVideosWatchedPipe):
    """ETL pipe for Instagram videos watched — v1 archive format.

    V1 files are a bare JSON array of ``{timestamp, media, label_values}``
    items.  The video URL is in ``label_values`` with ``label == "URL"``.
    """

    archive_version = 1
    archive_path_pattern = "ads_information/ads_and_topics/videos_watched.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramVideoWatchedRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                item = InstagramV1ActivityItem.model_validate(raw)
                video_url: str | None = None
                for lv in item.label_values:
                    if isinstance(lv, InstagramLabelValue) and lv.label == "URL":
                        video_url = lv.value
                        break
                    # TODO: parse Owner into attributedTo

                yield InstagramVideoWatchedRecord(
                    video_url=video_url,
                    timestamp=item.timestamp,
                    source=item.model_dump_json(),
                )
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=InstagramVideosWatchedPipe, memory=None))

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
from context_use.providers.instagram.schemas import Model as ActivityItem
from context_use.providers.instagram.utils import PROVIDER, fix_strings_recursive
from context_use.providers.instagram.videos_watched.record import (
    InstagramVideoWatchedRecord,
)
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class InstagramVideosWatchedPipe(Pipe[InstagramVideoWatchedRecord]):
    provider = PROVIDER
    interaction_type = "instagram_videos_watched"
    archive_version = 1
    archive_path_pattern = "ads_information/ads_and_topics/videos_watched.json"
    record_schema = InstagramVideoWatchedRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramVideoWatchedRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                item = ActivityItem.model_validate(fix_strings_recursive(raw))
                video_url: str | None = None
                for lv in item.label_values:
                    if lv.label == "URL":
                        video_url = lv.value
                        break

                yield InstagramVideoWatchedRecord(
                    video_url=video_url,
                    timestamp=item.timestamp,
                    source=item.model_dump_json(),
                )
        finally:
            stream.close()

    def transform(
        self,
        record: InstagramVideoWatchedRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)

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


declare_interaction(InteractionConfig(pipe=InstagramVideosWatchedPipe, memory=None))

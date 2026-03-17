from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime

from context_use.batch.grouper import WindowGrouper
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreViewObject,
    Video,
)
from context_use.memories.config import MemoryConfig
from context_use.memories.prompt.media import MediaMemoryPromptBuilder
from context_use.models.etl_task import EtlTask
from context_use.providers.netflix.schemas import PROVIDER
from context_use.providers.netflix.viewing_activity.record import (
    NetflixViewingActivityRecord,
)
from context_use.providers.netflix.viewing_activity.schemas import Model
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend


def _parse_datetime(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {value!r}")


class NetflixViewingActivityPipe(Pipe[NetflixViewingActivityRecord]):
    provider = PROVIDER
    interaction_type = "netflix_viewing_activity"
    archive_version = 1
    archive_path_pattern = "*/CONTENT_INTERACTION/ViewingActivity.csv"
    record_schema = NetflixViewingActivityRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[NetflixViewingActivityRecord]:
        stream = storage.open_stream(source_uri)
        try:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8"))
            for raw_row in reader:
                row = Model.model_validate(raw_row)
                if row.supplemental_video_type:
                    continue
                yield NetflixViewingActivityRecord(
                    profile_name=row.profile_name,
                    title=row.title,
                    start_time=row.start_time,
                    duration=row.duration,
                    country=row.country,
                    device_type=row.device_type,
                    bookmark=row.bookmark,
                    attributes=row.attributes,
                    source=json.dumps(raw_row),
                )
        finally:
            stream.close()

    def transform(
        self,
        record: NetflixViewingActivityRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = _parse_datetime(record.start_time)
        video = Video(name=record.title or None, published=published)  # type: ignore[reportCallIssue]
        payload = FibreViewObject(object=video, published=published)  # type: ignore[reportCallIssue]

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview("Netflix") or "",
            payload=payload.to_dict(),
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=published,
            source=record.source,
        )


declare_interaction(
    InteractionConfig(
        pipe=NetflixViewingActivityPipe,
        memory=MemoryConfig(
            prompt_builder=MediaMemoryPromptBuilder,
            grouper=WindowGrouper,
        ),
    )
)

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreDislike,
    FibreLike,
    Video,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.netflix.ratings.record import NetflixRatingsRecord
from context_use.providers.netflix.ratings.schemas import Model
from context_use.providers.netflix.schemas import PROVIDER
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

_LIKE_VALUES = frozenset({"2", "3"})
_DISLIKE_VALUES = frozenset({"1"})


def _parse_datetime(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {value!r}")


class NetflixRatingsPipe(Pipe[NetflixRatingsRecord]):
    provider = PROVIDER
    interaction_type = "netflix_ratings"
    archive_version = 1
    archive_path_pattern = "*/CONTENT_INTERACTION/Ratings.csv"
    record_schema = NetflixRatingsRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[NetflixRatingsRecord]:
        stream = storage.open_stream(source_uri)
        try:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8"))
            for raw_row in reader:
                row = Model.model_validate(raw_row)
                if row.thumbs_value not in _LIKE_VALUES | _DISLIKE_VALUES:
                    continue
                yield NetflixRatingsRecord(
                    profile_name=row.profile_name,
                    title_name=row.title_name,
                    thumbs_value=row.thumbs_value,
                    rating_type=row.rating_type,
                    event_utc_ts=row.event_utc_ts,
                    device_model=row.device_model,
                    source=json.dumps(raw_row),
                )
        finally:
            stream.close()

    def transform(
        self,
        record: NetflixRatingsRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = _parse_datetime(record.event_utc_ts)
        video = Video(name=record.title_name or None, published=published)  # type: ignore[reportCallIssue]

        if record.thumbs_value in _LIKE_VALUES:
            payload = FibreLike(object=video, published=published)  # type: ignore[reportCallIssue]
        else:
            payload = FibreDislike(object=video, published=published)  # type: ignore[reportCallIssue]

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


declare_interaction(InteractionConfig(pipe=NetflixRatingsPipe, memory=None))

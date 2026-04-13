from __future__ import annotations

import csv
import io
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
from context_use.providers.netflix.indicated_preferences.record import (
    NetflixIndicatedPreferencesRecord,
)
from context_use.providers.netflix.indicated_preferences.schemas import Model
from context_use.providers.netflix.schemas import PROVIDER
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


class NetflixIndicatedPreferencesPipe(Pipe[NetflixIndicatedPreferencesRecord]):
    provider = PROVIDER
    interaction_type = "netflix_indicated_preferences"
    archive_version = 1
    archive_path_pattern = "*/CONTENT_INTERACTION/IndicatedPreferences.csv"
    record_schema = NetflixIndicatedPreferencesRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[NetflixIndicatedPreferencesRecord]:
        stream = storage.open_stream(source_uri)
        try:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8"))
            for row in self._validated_items(reader, Model):
                yield NetflixIndicatedPreferencesRecord(
                    profile_name=row.profile_name,
                    show=row.show,
                    is_interested=row.is_interested,
                    event_date=row.event_date,
                    has_watched=row.has_watched,
                    source=row.model_dump_json(),
                )
        finally:
            stream.close()

    def transform(
        self,
        record: NetflixIndicatedPreferencesRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = _parse_datetime(record.event_date)
        video = Video(name=record.show or None, published=published)  # type: ignore[reportCallIssue]

        if record.is_interested.lower() == "true":
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


declare_interaction(
    InteractionConfig(pipe=NetflixIndicatedPreferencesPipe, memory=None)
)

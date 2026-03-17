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
    FibreSearch,
    Page,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.netflix.schemas import PROVIDER
from context_use.providers.netflix.search_history.record import (
    NetflixSearchHistoryRecord,
)
from context_use.providers.netflix.search_history.schemas import Model
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


class NetflixSearchHistoryPipe(Pipe[NetflixSearchHistoryRecord]):
    provider = PROVIDER
    interaction_type = "netflix_search_history"
    archive_version = 1
    archive_path_pattern = "*/CONTENT_INTERACTION/SearchHistory.csv"
    record_schema = NetflixSearchHistoryRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[NetflixSearchHistoryRecord]:
        stream = storage.open_stream(source_uri)
        try:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8"))
            for raw_row in reader:
                row = Model.model_validate(raw_row)
                yield NetflixSearchHistoryRecord(
                    profile_name=row.profile_name,
                    query_typed=row.query_typed,
                    displayed_name=row.displayed_name,
                    utc_timestamp=row.utc_timestamp,
                    action=row.action,
                    device=row.device,
                    country_iso_code=row.country_iso_code,
                    is_kids=row.is_kids,
                    source=json.dumps(raw_row),
                )
        finally:
            stream.close()

    def transform(
        self,
        record: NetflixSearchHistoryRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = _parse_datetime(record.utc_timestamp)
        name = record.query_typed or record.displayed_name or None
        page = Page(name=name, published=published)  # type: ignore[reportCallIssue]
        payload = FibreSearch(object=page, published=published)  # type: ignore[reportCallIssue]

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


declare_interaction(InteractionConfig(pipe=NetflixSearchHistoryPipe, memory=None))

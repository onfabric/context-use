from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreAddObjectToCollection,
    FibreCollection,
    Page,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.netflix.my_list.record import NetflixMyListRecord
from context_use.providers.netflix.my_list.schemas import Model
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


class NetflixMyListPipe(Pipe[NetflixMyListRecord]):
    provider = PROVIDER
    interaction_type = "netflix_my_list"
    archive_version = 1
    archive_path_pattern = "*/CONTENT_INTERACTION/MyList.csv"
    record_schema = NetflixMyListRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[NetflixMyListRecord]:
        stream = storage.open_stream(source_uri)
        try:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8"))
            for row in self._validated_items(reader, Model):
                yield NetflixMyListRecord(
                    profile_name=row.profile_name,
                    title_name=row.title_name,
                    utc_title_add_date=row.utc_title_add_date,
                    country=row.country,
                    source=row.model_dump_json(),
                )
        finally:
            stream.close()

    def transform(
        self,
        record: NetflixMyListRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = _parse_datetime(record.utc_title_add_date)
        page = Page(name=record.title_name or None, published=published)  # type: ignore[reportCallIssue]
        collection = FibreCollection(name="My List")  # type: ignore[reportCallIssue]
        payload = FibreAddObjectToCollection(  # type: ignore[reportCallIssue]
            object=page,
            target=collection,
            published=published,
        )

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


declare_interaction(InteractionConfig(pipe=NetflixMyListPipe, memory=None))

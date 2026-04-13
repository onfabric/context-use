from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    Application,
    FibreReceiveMessage,
    FibreTextMessage,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.netflix.messages_from_netflix.record import (
    NetflixMessagesRecord,
)
from context_use.providers.netflix.messages_from_netflix.schemas import Model
from context_use.providers.netflix.schemas import PROVIDER
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

_NETFLIX_APP = Application(name="Netflix")  # type: ignore[reportCallIssue]


def _parse_datetime(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {value!r}")


class NetflixMessagesPipe(Pipe[NetflixMessagesRecord]):
    provider = PROVIDER
    interaction_type = "netflix_messages_from_netflix"
    archive_version = 1
    archive_path_pattern = "*/MESSAGES/MessagesSentByNetflix.csv"
    record_schema = NetflixMessagesRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[NetflixMessagesRecord]:
        stream = storage.open_stream(source_uri)
        try:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8"))
            for row in self._validated_items(reader, Model):
                if not row.message_name and not row.title_name:
                    continue
                yield NetflixMessagesRecord(
                    profile_name=row.profile_name,
                    message_name=row.message_name,
                    title_name=row.title_name,
                    channel=row.channel,
                    sent_utc_ts=row.sent_utc_ts,
                    country_iso_code=row.country_iso_code,
                    device_model=row.device_model,
                    source=row.model_dump_json(),
                )
        finally:
            stream.close()

    def transform(
        self,
        record: NetflixMessagesRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = _parse_datetime(record.sent_utc_ts)
        content = record.message_name or record.title_name
        message = FibreTextMessage(content=content, published=published)  # type: ignore[reportCallIssue]
        payload = FibreReceiveMessage(  # type: ignore[reportCallIssue]
            object=message,
            actor=_NETFLIX_APP,
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


declare_interaction(InteractionConfig(pipe=NetflixMessagesPipe, memory=None))

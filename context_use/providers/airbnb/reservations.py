from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

from context_use.batch.grouper import WindowGrouper
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreAddObjectToCollection,
    FibreCollection,
    Page,
)
from context_use.memories.config import MemoryConfig
from context_use.memories.prompt.media import MediaMemoryPromptBuilder
from context_use.models.etl_task import EtlTask
from context_use.providers.airbnb.schemas import PROVIDER, AirbnbReservationRecord
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)

_TRIPS_COLLECTION = FibreCollection(name="Trips")  # type: ignore[reportCallIssue]


class AirbnbReservationsPipe(Pipe[AirbnbReservationRecord]):
    """ETL pipe for Airbnb reservations.

    Reads ``reservations.json`` and emits one record per booking.
    ``bookingSessions`` are skipped (metadata only).
    """

    provider = PROVIDER
    interaction_type = "airbnb_reservations"
    archive_version = 1
    archive_path_pattern = "*/json/reservations.json"
    record_schema = AirbnbReservationRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[AirbnbReservationRecord]:
        raw = storage.read(source_uri)
        data = json.loads(raw)

        for top_level in data:
            for res in top_level.get("reservations", []):
                hosting_url = res.get("hostingUrl")
                start_date = res.get("startDate")
                created_at = res.get("createdAt")
                confirmation_code = res.get("confirmationCode")
                if not hosting_url or not start_date or not created_at:
                    continue

                yield AirbnbReservationRecord(
                    confirmation_code=confirmation_code or "",
                    hosting_url=hosting_url,
                    start_date=start_date,
                    nights=res.get("nights", 0),
                    number_of_guests=res.get("numberOfGuests", 1),
                    status=res.get("status", "unknown"),
                    message=res.get("message"),
                    created_at=created_at,
                    source=json.dumps(res, default=str),
                )

    def transform(
        self,
        record: AirbnbReservationRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromisoformat(record.created_at)
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)

        name = (
            f"{record.nights}-night stay starting {record.start_date} ({record.status})"
        )
        page = Page(  # type: ignore[reportCallIssue]
            name=name,
            url=record.hosting_url,
            published=published,
        )

        payload = FibreAddObjectToCollection(  # type: ignore[reportCallIssue]
            object=page,
            target=_TRIPS_COLLECTION,
            published=published,
        )

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview("Airbnb") or "",
            payload=payload.to_dict(),
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=published,
            source=record.source,
        )


declare_interaction(
    InteractionConfig(
        pipe=AirbnbReservationsPipe,
        memory=MemoryConfig(
            prompt_builder=MediaMemoryPromptBuilder,
            grouper=WindowGrouper,
        ),
    )
)

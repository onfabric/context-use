from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import datetime

import ijson

from context_use.activitystreams.objects import Page
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreViewObject,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.airbnb.reservations.record import AirbnbReservationRecord
from context_use.providers.airbnb.reservations.schemas import Model
from context_use.providers.airbnb.schemas import PROVIDER
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def _parse_timestamp(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


class AirbnbReservationsPipe(Pipe[AirbnbReservationRecord]):
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
        stream = storage.open_stream(source_uri)
        try:
            for raw_item in ijson.items(stream, "item"):
                envelope = Model.model_validate(raw_item)
                for reservation in envelope.reservations:
                    yield AirbnbReservationRecord(
                        confirmation_code=reservation.confirmationCode,
                        hosting_url=reservation.hostingUrl,
                        start_date=reservation.startDate,
                        nights=reservation.nights,
                        number_of_guests=reservation.numberOfGuests,
                        number_of_adults=reservation.numberOfAdults,
                        number_of_children=reservation.numberOfChildren,
                        number_of_infants=reservation.numberOfInfants,
                        status=reservation.status,
                        created_at=reservation.createdAt,
                        message=reservation.message,
                        source=json.dumps(reservation.model_dump(), default=str),
                    )
        finally:
            stream.close()

    def transform(
        self,
        record: AirbnbReservationRecord,
        task: EtlTask,
    ) -> ThreadRow:
        name = f"{record.nights}-night stay from {record.start_date}"
        page = Page(name=name, url=record.hosting_url)  # type: ignore[reportCallIssue]
        published = _parse_timestamp(record.created_at)

        payload = FibreViewObject(  # type: ignore[reportCallIssue]
            object=page,
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


declare_interaction(InteractionConfig(pipe=AirbnbReservationsPipe, memory=None))

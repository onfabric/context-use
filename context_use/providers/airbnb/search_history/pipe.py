from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import ijson

from context_use.activitystreams.objects import Page
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreSearch,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.airbnb.schemas import PROVIDER
from context_use.providers.airbnb.search_history.record import AirbnbSearchRecord
from context_use.providers.airbnb.search_history.schemas import Model
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def _parse_timestamp(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class AirbnbSearchHistoryPipe(Pipe[AirbnbSearchRecord]):
    provider = PROVIDER
    interaction_type = "airbnb_search_history"
    archive_version = 1
    archive_path_pattern = "*/json/search_history.json"
    record_schema = AirbnbSearchRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[AirbnbSearchRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for envelope in self._validated_items(ijson.items(stream, "item"), Model):
                for datum in envelope.servicedata:
                    yield AirbnbSearchRecord(
                        city=datum.city,
                        country=datum.country,
                        state=datum.state,
                        checkin_date=datum.checkindate,
                        checkout_date=datum.checkoutdate,
                        number_of_guests=datum.numberofguests,
                        number_of_nights=datum.numberofnights,
                        time_of_search=datum.timeofsearch,
                        raw_location=datum.rawlocation,
                        source=json.dumps(datum.model_dump(), default=str),
                    )
        finally:
            stream.close()

    def transform(
        self,
        record: AirbnbSearchRecord,
        task: EtlTask,
    ) -> ThreadRow:
        name = record.city or record.raw_location or "unknown"
        page = Page(name=name)  # type: ignore[reportCallIssue]
        published = _parse_timestamp(record.time_of_search)

        payload = FibreSearch(  # type: ignore[reportCallIssue]
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


declare_interaction(InteractionConfig(pipe=AirbnbSearchHistoryPipe, memory=None))

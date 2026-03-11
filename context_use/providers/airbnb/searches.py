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
    FibreSearch,
    Page,
)
from context_use.memories.config import MemoryConfig
from context_use.memories.prompt.media import MediaMemoryPromptBuilder
from context_use.models.etl_task import EtlTask
from context_use.providers.airbnb.schemas import PROVIDER, AirbnbSearchRecord
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class AirbnbSearchesPipe(Pipe[AirbnbSearchRecord]):
    """ETL pipe for Airbnb search history.

    Reads ``search_history.json`` and emits one record per location
    search.  The ``rawlocation`` field is used as the search term.
    """

    provider = PROVIDER
    interaction_type = "airbnb_searches"
    archive_version = 1
    archive_path_pattern = "*/json/search_history.json"
    record_schema = AirbnbSearchRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[AirbnbSearchRecord]:
        raw = storage.read(source_uri)
        data = json.loads(raw)

        for top_level in data:
            for entry in top_level.get("servicedata", []):
                raw_location = entry.get("rawlocation")
                time_of_search = entry.get("timeofsearch")
                if not raw_location or not time_of_search:
                    continue

                yield AirbnbSearchRecord(
                    raw_location=raw_location,
                    city=entry.get("city"),
                    country=entry.get("country"),
                    checkin_date=entry.get("checkindate"),
                    checkout_date=entry.get("checkoutdate"),
                    number_of_guests=entry.get("numberofguests"),
                    time_of_search=time_of_search,
                    source=json.dumps(entry, default=str),
                )

    def transform(
        self,
        record: AirbnbSearchRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.strptime(record.time_of_search, "%Y-%m-%d %H:%M:%S")
        published = published.replace(tzinfo=UTC)

        name = record.raw_location
        if record.checkin_date:
            name += f" ({record.checkin_date}"
            if record.checkout_date:
                name += f" to {record.checkout_date}"
            name += ")"

        page = Page(  # type: ignore[reportCallIssue]
            name=name,
            published=published,
        )

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


declare_interaction(
    InteractionConfig(
        pipe=AirbnbSearchesPipe,
        memory=MemoryConfig(
            prompt_builder=MediaMemoryPromptBuilder,
            grouper=WindowGrouper,
        ),
    )
)

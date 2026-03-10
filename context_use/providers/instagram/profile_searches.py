import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreSearch,
    Profile,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.schemas import (
    PROVIDER,
    InstagramHrefTimestampSchema,
    InstagramProfileSearchRecord,
    InstagramStringListDataWrapper,
)
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)

_SearchItem = InstagramStringListDataWrapper[InstagramHrefTimestampSchema]


class InstagramProfileSearchesPipe(Pipe[InstagramProfileSearchRecord]):
    """ETL pipe for Instagram profile searches.

    Reads ``searches_user`` from
    ``logged_information/recent_searches/profile_searches.json``.
    Each item has ``{string_list_data: [{href, value, timestamp}]}``.
    Creates ``FibreSearch(object=Profile(...))``.
    """

    provider = PROVIDER
    interaction_type = "instagram_profile_searches"
    archive_version = 1
    archive_path_pattern = "logged_information/recent_searches/profile_searches.json"
    record_schema = InstagramProfileSearchRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramProfileSearchRecord]:
        raw = storage.read(source_uri)
        data = json.loads(raw)
        items = data.get("searches_user", [])
        for raw_item in items:
            parsed = _SearchItem.model_validate(raw_item)
            title = raw_item.get("title")
            for entry in parsed.string_list_data:
                username = entry.value or title
                # Skip entries with no username — preview would be unusable
                if not username:
                    continue
                yield InstagramProfileSearchRecord(
                    username=username,
                    href=entry.href,
                    timestamp=entry.timestamp,
                    source=json.dumps(raw_item),
                )

    def transform(
        self,
        record: InstagramProfileSearchRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)

        profile_kwargs: dict = {}
        if record.username:
            profile_kwargs["name"] = record.username
        if record.href:
            profile_kwargs["url"] = record.href

        profile = Profile(**profile_kwargs)  # type: ignore[reportCallIssue]

        payload = FibreSearch(  # type: ignore[reportCallIssue]
            object=profile,
            published=published,
        )

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview(task.provider) or "",
            payload=payload.to_dict(),
            source=record.source,
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=published,
        )


declare_interaction(InteractionConfig(pipe=InstagramProfileSearchesPipe, memory=None))

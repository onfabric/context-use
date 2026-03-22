from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import ijson

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreAd,
    FibreClickAdObject,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.ads_clicked.record import (
    InstagramAdsClickedRecord,
)
from context_use.providers.instagram.ads_clicked.schemas import Model
from context_use.providers.instagram.schemas import PROVIDER, _fix_strings_recursive
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend


class InstagramAdsClickedPipe(Pipe[InstagramAdsClickedRecord]):
    provider = PROVIDER
    interaction_type = "instagram_ads_clicked"
    archive_version = 1
    archive_path_pattern = "ads_information/ads_and_topics/ads_clicked.json"
    record_schema = InstagramAdsClickedRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramAdsClickedRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                item = Model.model_validate(_fix_strings_recursive(raw))
                ad_url: str | None = None
                title: str | None = None

                for lv in item.label_values:
                    if lv.label == "URL":
                        ad_url = lv.value
                    elif lv.label == "Title":
                        title = lv.value

                yield InstagramAdsClickedRecord(
                    title=title,
                    ad_url=ad_url,
                    timestamp=item.timestamp,
                    source=item.model_dump_json(by_alias=True),
                )
        finally:
            stream.close()

    def transform(
        self,
        record: InstagramAdsClickedRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)

        ad_kwargs: dict = {}
        if record.ad_url:
            ad_kwargs["url"] = record.ad_url
        if record.title:
            ad_kwargs["name"] = record.title

        ad = FibreAd(**ad_kwargs)  # type: ignore[reportCallIssue]

        payload = FibreClickAdObject(  # type: ignore[reportCallIssue]
            object=ad,
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


declare_interaction(InteractionConfig(pipe=InstagramAdsClickedPipe, memory=None))

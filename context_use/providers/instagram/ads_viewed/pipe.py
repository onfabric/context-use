from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import ijson

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreAd,
    FibreViewAdObject,
    Profile,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.ads_viewed.record import (
    InstagramAdsViewedRecord,
)
from context_use.providers.instagram.ads_viewed.schemas import LabelValue, Model
from context_use.providers.instagram.schemas import PROVIDER, _fix_strings_recursive
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend


def _extract_owner_username(lv: LabelValue) -> str | None:
    if lv.dict_ is None:
        return None
    for group in lv.dict_:
        for entry in group.dict_:
            if entry.label == "Username":
                return entry.value
    return None


class InstagramAdsViewedPipe(Pipe[InstagramAdsViewedRecord]):
    provider = PROVIDER
    interaction_type = "instagram_ads_viewed"
    archive_version = 1
    archive_path_pattern = "ads_information/ads_and_topics/ads_viewed.json"
    record_schema = InstagramAdsViewedRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramAdsViewedRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                item = Model.model_validate(_fix_strings_recursive(raw))
                ad_url: str | None = None
                author: str | None = None

                for lv in item.label_values:
                    if lv.label == "URL":
                        ad_url = lv.value
                    elif lv.dict_ is not None and lv.title == "Owner":
                        author = _extract_owner_username(lv)

                yield InstagramAdsViewedRecord(
                    author=author,
                    ad_url=ad_url,
                    timestamp=item.timestamp,
                    source=item.model_dump_json(by_alias=True),
                )
        finally:
            stream.close()

    def transform(
        self,
        record: InstagramAdsViewedRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)

        ad_kwargs: dict = {}
        if record.ad_url:
            ad_kwargs["url"] = record.ad_url
        if record.author:
            ad_kwargs["attributedTo"] = Profile(  # type: ignore[reportCallIssue]
                name=record.author,
                url=f"https://www.instagram.com/{record.author}",
            )

        ad = FibreAd(**ad_kwargs)  # type: ignore[reportCallIssue]

        payload = FibreViewAdObject(  # type: ignore[reportCallIssue]
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


declare_interaction(InteractionConfig(pipe=InstagramAdsViewedPipe, memory=None))

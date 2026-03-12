from __future__ import annotations

from collections.abc import Iterator

import ijson

from context_use.providers.instagram.schemas import (
    InstagramLabelValue,
    InstagramV1ActivityItem,
)
from context_use.providers.instagram.videos_watched.pipe import (
    _InstagramVideosWatchedPipe,
)
from context_use.providers.instagram.videos_watched.record import (
    InstagramVideoWatchedRecord,
)
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend


class InstagramVideosWatchedPipe(_InstagramVideosWatchedPipe):
    archive_version = 1
    archive_path_pattern = "ads_information/ads_and_topics/videos_watched.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramVideoWatchedRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                item = InstagramV1ActivityItem.model_validate(raw)
                video_url: str | None = None
                for lv in item.label_values:
                    if isinstance(lv, InstagramLabelValue) and lv.label == "URL":
                        video_url = lv.value
                        break

                yield InstagramVideoWatchedRecord(
                    video_url=video_url,
                    timestamp=item.timestamp,
                    source=item.model_dump_json(),
                )
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=InstagramVideosWatchedPipe, memory=None))

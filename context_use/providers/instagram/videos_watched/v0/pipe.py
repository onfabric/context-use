from __future__ import annotations

from collections.abc import Iterator

from context_use.providers.instagram.videos_watched.pipe import (
    InstagramVideosWatchedPipe,
)
from context_use.providers.instagram.videos_watched.record import (
    InstagramVideoWatchedRecord,
)
from context_use.providers.instagram.videos_watched.v0.schemas import (
    InstagramVideosWatchedV0Manifest,
)
from context_use.storage.base import StorageBackend


class InstagramVideosWatchedV0Pipe(InstagramVideosWatchedPipe):
    archive_version = 0
    archive_path_pattern = "ads_information/ads_and_topics/videos_watched.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramVideoWatchedRecord]:
        raw = storage.read(source_uri)
        manifest = InstagramVideosWatchedV0Manifest.model_validate_json(raw)
        for item in manifest.impressions_history_videos_watched:
            yield InstagramVideoWatchedRecord(
                author=item.string_map_data.Author.value,
                timestamp=item.string_map_data.Time.timestamp,
                source=item.model_dump_json(),
            )

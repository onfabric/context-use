from __future__ import annotations

from collections.abc import Iterator

from context_use.providers.instagram.posts_viewed.pipe import _InstagramPostsViewedPipe
from context_use.providers.instagram.posts_viewed.record import (
    InstagramPostsViewedRecord,
)
from context_use.providers.instagram.posts_viewed.v0.schemas import (
    InstagramPostsViewedManifest,
)
from context_use.storage.base import StorageBackend


class InstagramPostsViewedPipe(_InstagramPostsViewedPipe):
    archive_version = 0
    archive_path_pattern = "ads_information/ads_and_topics/posts_viewed.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramPostsViewedRecord]:
        raw = storage.read(source_uri)
        manifest = InstagramPostsViewedManifest.model_validate_json(raw)
        for item in manifest.impressions_history_posts_seen:
            yield InstagramPostsViewedRecord(
                author=item.string_map_data.Author.value,
                timestamp=item.string_map_data.Time.timestamp,
                source=item.model_dump_json(),
            )

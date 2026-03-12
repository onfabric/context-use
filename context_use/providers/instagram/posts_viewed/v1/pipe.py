from __future__ import annotations

from collections.abc import Iterator

import ijson

from context_use.providers.instagram.posts_viewed.pipe import _InstagramPostsViewedPipe
from context_use.providers.instagram.posts_viewed.record import (
    InstagramPostsViewedRecord,
)
from context_use.providers.instagram.schemas import (
    InstagramLabelValue,
    InstagramV1ActivityItem,
    InstagramV1OwnerEntry,
    extract_owner_username,
)
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend


class InstagramPostsViewedPipe(_InstagramPostsViewedPipe):
    archive_version = 1
    archive_path_pattern = "ads_information/ads_and_topics/posts_viewed.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramPostsViewedRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                item = InstagramV1ActivityItem.model_validate(raw)
                post_url: str | None = None
                author: str | None = None

                for lv in item.label_values:
                    if isinstance(lv, InstagramLabelValue):
                        if lv.label == "URL":
                            post_url = lv.value
                    elif isinstance(lv, InstagramV1OwnerEntry) and lv.title == "Owner":
                        author = extract_owner_username(lv)

                yield InstagramPostsViewedRecord(
                    author=author,
                    post_url=post_url,
                    timestamp=item.timestamp,
                    source=item.model_dump_json(),
                )
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=InstagramPostsViewedPipe, memory=None))

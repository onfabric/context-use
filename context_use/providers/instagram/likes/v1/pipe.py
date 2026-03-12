from __future__ import annotations

from collections.abc import Iterator

import ijson

from context_use.providers.instagram.likes.pipe import InstagramLikePipe
from context_use.providers.instagram.likes.record import InstagramLikedPostRecord
from context_use.providers.instagram.schemas import (
    InstagramLabelValue,
    InstagramV1ActivityItem,
    InstagramV1OwnerEntry,
    extract_owner_username,
)
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend


def _extract_like_item(item: InstagramV1ActivityItem) -> InstagramLikedPostRecord:
    href: str | None = None
    title: str | None = None
    for lv in item.label_values:
        if isinstance(lv, InstagramLabelValue):
            if lv.label == "URL":
                href = lv.href or lv.value
        elif isinstance(lv, InstagramV1OwnerEntry) and lv.title == "Owner":
            title = extract_owner_username(lv)
    return InstagramLikedPostRecord(
        title=title or "",
        href=href,
        timestamp=item.timestamp,
        source=item.model_dump_json(),
    )


class InstagramLikedPostsPipe(InstagramLikePipe):
    interaction_type = "instagram_liked_posts"
    archive_version = 1
    archive_path_pattern = "your_instagram_activity/likes/liked_posts.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramLikedPostRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                yield _extract_like_item(InstagramV1ActivityItem.model_validate(raw))
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=InstagramLikedPostsPipe, memory=None))

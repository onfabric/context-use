from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import ijson

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibrePost,
    FibreViewObject,
    Profile,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.posts_viewed.record import (
    InstagramPostsViewedRecord,
)
from context_use.providers.instagram.schemas import Model as ActivityItem
from context_use.providers.instagram.utils import (
    PROVIDER,
    extract_owner_username,
    fix_strings_recursive,
)
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class InstagramPostsViewedPipe(Pipe[InstagramPostsViewedRecord]):
    provider = PROVIDER
    interaction_type = "instagram_posts_viewed"
    archive_version = 1
    archive_path_pattern = "ads_information/ads_and_topics/posts_viewed.json"
    record_schema = InstagramPostsViewedRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramPostsViewedRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                item = ActivityItem.model_validate(fix_strings_recursive(raw))
                post_url: str | None = None
                author: str | None = None

                for lv in item.label_values:
                    if lv.label == "URL":
                        post_url = lv.value
                    else:
                        owner = extract_owner_username(lv)
                        if owner:
                            author = owner

                yield InstagramPostsViewedRecord(
                    author=author,
                    post_url=post_url,
                    timestamp=item.timestamp,
                    source=item.model_dump_json(),
                )
        finally:
            stream.close()

    def transform(
        self,
        record: InstagramPostsViewedRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)

        post_kwargs: dict = {}
        if record.post_url:
            post_kwargs["url"] = record.post_url
        if record.author:
            post_kwargs["attributedTo"] = Profile(  # type: ignore[reportCallIssue]
                name=record.author,
                url=f"https://www.instagram.com/{record.author}",
            )

        post = FibrePost(**post_kwargs)  # type: ignore[reportCallIssue]

        payload = FibreViewObject(  # type: ignore[reportCallIssue]
            object=post,
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


declare_interaction(InteractionConfig(pipe=InstagramPostsViewedPipe, memory=None))

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime

from pydantic import TypeAdapter

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibrePost,
    FibreViewObject,
    Profile,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.schemas import (
    PROVIDER,
    InstagramLabelValue,
    InstagramPostsViewedRecord,
    InstagramPostsViewedV0Manifest,
    InstagramV1ActivityItem,
    InstagramV1OwnerEntry,
    extract_owner_username,
)
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)

_v1_activity_list = TypeAdapter(list[InstagramV1ActivityItem])


class _InstagramPostsViewedPipe(Pipe[InstagramPostsViewedRecord]):
    """Shared transform logic for Instagram posts viewed (v0 and v1).

    Subclasses implement :meth:`extract_file` to parse their specific
    archive format; :meth:`transform` is inherited.
    """

    provider = PROVIDER
    interaction_type = "instagram_posts_viewed"
    record_schema = InstagramPostsViewedRecord

    def transform(
        self,
        record: InstagramPostsViewedRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)

        # Build the FibrePost — author becomes attributedTo Profile
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


class InstagramPostsViewedV0Pipe(_InstagramPostsViewedPipe):
    """ETL pipe for Instagram posts viewed — v0 archive format.

    V0 files contain a top-level ``impressions_history_posts_seen``
    key wrapping an array of ``{string_map_data: {Author, Time}}`` items.
    """

    archive_version = 0
    archive_path_pattern = "ads_information/ads_and_topics/posts_viewed.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramPostsViewedRecord]:
        raw = storage.read(source_uri)
        manifest = InstagramPostsViewedV0Manifest.model_validate_json(raw)
        for item in manifest.impressions_history_posts_seen:
            yield InstagramPostsViewedRecord(
                author=item.string_map_data.Author.value,
                timestamp=item.string_map_data.Time.timestamp,
                source=item.model_dump_json(),
            )


class InstagramPostsViewedPipe(_InstagramPostsViewedPipe):
    """ETL pipe for Instagram posts viewed — v1 archive format.

    V1 files are a bare JSON array of ``{timestamp, media, label_values}``
    items.  The post URL is in ``label_values`` with ``label == "URL"``,
    and the author username is nested inside an ``Owner`` dict entry.
    """

    archive_version = 1
    archive_path_pattern = "ads_information/ads_and_topics/posts_viewed.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramPostsViewedRecord]:
        raw = storage.read(source_uri)
        items = _v1_activity_list.validate_json(raw)
        for item in items:
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


declare_interaction(InteractionConfig(pipe=InstagramPostsViewedPipe, memory=None))

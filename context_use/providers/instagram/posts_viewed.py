from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

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
    InstagramAuthorSchema,
    InstagramLabelValue,
    InstagramPostsViewedRecord,
    InstagramStringMapDataWrapper,
)
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)

# V0 wrapper type alias — same shape as videos_watched v0
_V0Item = InstagramStringMapDataWrapper[InstagramAuthorSchema]


class _InstagramPostsViewedPipe(Pipe[InstagramPostsViewedRecord]):
    """Shared transform logic for Instagram posts viewed (v0 and v1).

    Subclasses implement :meth:`extract_file` to parse their specific
    archive format; :meth:`transform` is inherited.
    """

    provider = "instagram"
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
        data = json.loads(raw)
        items = data.get("impressions_history_posts_seen", [])
        for raw_item in items:
            parsed = _V0Item.model_validate(raw_item)
            yield InstagramPostsViewedRecord(
                author=parsed.string_map_data.Author.value,
                timestamp=parsed.string_map_data.Time.timestamp,
                source=json.dumps(raw_item),
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
        items: list[dict] = json.loads(raw)
        for raw_item in items:
            timestamp = raw_item.get("timestamp")
            if timestamp is None:
                continue

            post_url: str | None = None
            author: str | None = None

            for lv_data in raw_item.get("label_values", []):
                # Simple label_value entries have "label"
                if "label" in lv_data:
                    lv = InstagramLabelValue.model_validate(lv_data)
                    if lv.label == "URL":
                        post_url = lv.value

                # Nested Owner dict: {title: "Owner", dict: [{dict: [...]}]}
                if lv_data.get("title") == "Owner":
                    author = self._extract_owner_username(lv_data)

            yield InstagramPostsViewedRecord(
                author=author,
                post_url=post_url,
                timestamp=timestamp,
                source=json.dumps(raw_item),
            )

    @staticmethod
    def _extract_owner_username(owner_data: dict) -> str | None:
        """Extract the username from the nested Owner dict structure.

        The Owner entry looks like::

            {
                "title": "Owner",
                "dict": [
                    {
                        "title": "",
                        "dict": [
                            {"label": "Username", "value": "some_user"},
                            {"label": "Name", "value": "Some User"},
                            ...
                        ]
                    }
                ]
            }
        """
        for outer in owner_data.get("dict", []):
            for inner in outer.get("dict", []):
                if inner.get("label") == "Username":
                    return inner.get("value")
        return None


POSTS_VIEWED_V0_CONFIG = InteractionConfig(
    pipe=InstagramPostsViewedV0Pipe,
    memory=None,
)

POSTS_VIEWED_V1_CONFIG = InteractionConfig(
    pipe=InstagramPostsViewedPipe,
    memory=None,
)

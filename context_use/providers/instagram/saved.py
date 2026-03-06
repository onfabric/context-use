from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreAddObjectToCollection,
    FibreCollection,
    FibreCollectionFavourites,
    FibrePost,
    Profile,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.schemas import (
    InstagramSavedCollectionRecord,
    InstagramSavedPostRecord,
)
from context_use.providers.registry import register_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# saved_posts — straightforward single-file pipe
# ---------------------------------------------------------------------------


class InstagramSavedPostsPipe(Pipe[InstagramSavedPostRecord]):
    """ETL pipe for Instagram saved posts.

    Reads ``saved_saved_media`` from
    ``your_instagram_activity/saved/saved_posts.json``.
    Each item has ``{title, string_map_data: {"Saved on": {href, timestamp}}}``.
    Creates ``FibreAddObjectToCollection(object=FibrePost(...),
    target=FibreCollectionFavourites())``.
    """

    provider = "instagram"
    interaction_type = "instagram_saved_posts"
    archive_version = 1
    archive_path_pattern = "your_instagram_activity/saved/saved_posts.json"
    record_schema = InstagramSavedPostRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramSavedPostRecord]:
        raw = storage.read(source_uri)
        data = json.loads(raw)

        for raw_item in data.get("saved_saved_media", []):
            title = raw_item.get("title", "")
            smd = raw_item.get("string_map_data", {})
            saved_on = smd.get("Saved on", {})

            timestamp = saved_on.get("timestamp")
            if timestamp is None:
                continue

            yield InstagramSavedPostRecord(
                title=title,
                href=saved_on.get("href"),
                timestamp=timestamp,
                source=json.dumps(raw_item),
            )

    def transform(
        self,
        record: InstagramSavedPostRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)

        post_kwargs: dict = {}
        if record.href:
            post_kwargs["url"] = record.href
        if record.title:
            post_kwargs["attributedTo"] = Profile(  # type: ignore[reportCallIssue]
                name=record.title,
            )

        post = FibrePost(**post_kwargs)  # type: ignore[reportCallIssue]

        payload = FibreAddObjectToCollection(  # type: ignore[reportCallIssue]
            object=post,
            target=FibreCollectionFavourites(),  # type: ignore[reportCallIssue]
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


# ---------------------------------------------------------------------------
# saved_collections — stateful extraction (interleaved headers + items)
# ---------------------------------------------------------------------------


class InstagramSavedCollectionsPipe(Pipe[InstagramSavedCollectionRecord]):
    """ETL pipe for Instagram saved collections.

    Reads ``saved_saved_collections`` from
    ``your_instagram_activity/saved/saved_collections.json``.

    The array interleaves collection headers and child items:

    - **Header**: ``{title: "Collection", string_map_data: {Name, "Creation Time", ...}}``
    - **Item**: ``{string_map_data: {Name: {value, href}, "Added Time": {...}}}``

    The pipe tracks the "current collection" while iterating.  Items
    that appear before any header are skipped with a warning.
    """  # noqa: E501

    provider = "instagram"
    interaction_type = "instagram_saved_collections"
    archive_version = 1
    archive_path_pattern = "your_instagram_activity/saved/saved_collections.json"
    record_schema = InstagramSavedCollectionRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramSavedCollectionRecord]:
        raw = storage.read(source_uri)
        data = json.loads(raw)

        current_collection: tuple[str, int] | None = None  # (name, created)

        for raw_item in data.get("saved_saved_collections", []):
            smd = raw_item.get("string_map_data", {})

            # --- Collection header ---
            if "Creation Time" in smd:
                name = smd.get("Name", {}).get("value", "")
                created = smd["Creation Time"].get("timestamp")
                if name and created is not None:
                    current_collection = (name, created)
                continue

            # --- Child item ---
            if "Added Time" not in smd:
                continue

            if current_collection is None:
                logger.warning(
                    "%s: skipping orphan item before any collection header",
                    self.__class__.__name__,
                )
                continue

            name_entry = smd.get("Name", {})
            item_author = name_entry.get("value", "")
            if not item_author:
                continue

            item_href = name_entry.get("href")
            item_added_at = smd["Added Time"].get("timestamp")
            if item_added_at is None:
                continue

            coll_name, coll_created = current_collection

            yield InstagramSavedCollectionRecord(
                collection_name=coll_name,
                collection_created_at=coll_created,
                item_author=item_author,
                item_href=item_href,
                item_added_at=item_added_at,
                source=json.dumps(raw_item),
            )

    def transform(
        self,
        record: InstagramSavedCollectionRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.item_added_at), tz=UTC)
        collection_published = datetime.fromtimestamp(
            float(record.collection_created_at), tz=UTC
        )

        post_kwargs: dict = {}
        if record.item_href:
            post_kwargs["url"] = record.item_href
        post_kwargs["attributedTo"] = Profile(  # type: ignore[reportCallIssue]
            name=record.item_author,
        )

        post = FibrePost(**post_kwargs)  # type: ignore[reportCallIssue]

        target = FibreCollection(  # type: ignore[reportCallIssue]
            name=record.collection_name,
            published=collection_published,
        )

        payload = FibreAddObjectToCollection(  # type: ignore[reportCallIssue]
            object=post,
            target=target,
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


register_interaction(InteractionConfig(pipe=InstagramSavedPostsPipe, memory=None))
register_interaction(InteractionConfig(pipe=InstagramSavedCollectionsPipe, memory=None))

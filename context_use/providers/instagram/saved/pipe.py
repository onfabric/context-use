from __future__ import annotations

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
from context_use.providers.instagram.saved.record import (
    InstagramSavedCollectionRecord,
    InstagramSavedPostRecord,
)
from context_use.providers.instagram.saved.schemas_saved_collections import (
    Model as SavedCollectionsManifest,
)
from context_use.providers.instagram.saved.schemas_saved_posts import (
    Model as SavedPostsManifest,
)
from context_use.providers.instagram.schemas import PROVIDER
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class InstagramSavedPostsPipe(Pipe[InstagramSavedPostRecord]):
    provider = PROVIDER
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
        manifest = SavedPostsManifest.model_validate_json(raw)

        for item in manifest.saved_saved_media:
            timestamp = item.string_map_data.Saved_on.timestamp
            if timestamp is None:
                continue
            yield InstagramSavedPostRecord(
                title=item.title,
                href=item.string_map_data.Saved_on.href,
                timestamp=timestamp,
                source=item.model_dump_json(),
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


class InstagramSavedCollectionsPipe(Pipe[InstagramSavedCollectionRecord]):
    provider = PROVIDER
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
        manifest = SavedCollectionsManifest.model_validate_json(raw)

        current_collection: tuple[str, int] | None = None  # (name, created)

        for item in manifest.saved_saved_collections:
            smd = item.string_map_data

            # --- Collection header (has Creation_Time) ---
            if smd.Creation_Time is not None:
                name_val = smd.Name_1.value
                if name_val:
                    current_collection = (name_val, smd.Creation_Time.timestamp)
                continue

            # --- Child item (has Added_Time) ---
            if smd.Added_Time is None:
                continue

            if current_collection is None:
                logger.warning(
                    "%s: skipping orphan item before any collection header",
                    self.__class__.__name__,
                )
                continue

            item_author = smd.Name_1.value
            if not item_author:
                continue

            item_href = smd.Name_1.href
            coll_name, coll_created = current_collection

            yield InstagramSavedCollectionRecord(
                collection_name=coll_name,
                collection_created_at=coll_created,
                item_author=item_author,
                item_href=item_href,
                item_added_at=smd.Added_Time.timestamp,
                source=item.model_dump_json(),
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


declare_interaction(InteractionConfig(pipe=InstagramSavedPostsPipe, memory=None))
declare_interaction(InteractionConfig(pipe=InstagramSavedCollectionsPipe, memory=None))

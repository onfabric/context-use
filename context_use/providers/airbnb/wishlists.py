from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

from context_use.batch.grouper import WindowGrouper
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreAddObjectToCollection,
    FibreCollection,
    Page,
)
from context_use.memories.config import MemoryConfig
from context_use.memories.prompt.media import MediaMemoryPromptBuilder
from context_use.models.etl_task import EtlTask
from context_use.providers.airbnb.schemas import PROVIDER, AirbnbWishlistItemRecord
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class AirbnbWishlistsPipe(Pipe[AirbnbWishlistItemRecord]):
    """ETL pipe for Airbnb wishlists.

    Reads ``wishlists.json`` and emits one record per saved listing.
    Bot-created wishlists (``wishlistType != "WISHLIST"``) are skipped.
    """

    provider = PROVIDER
    interaction_type = "airbnb_wishlists"
    archive_version = 1
    archive_path_pattern = "*/json/wishlists.json"
    record_schema = AirbnbWishlistItemRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[AirbnbWishlistItemRecord]:
        raw = storage.read(source_uri)
        data = json.loads(raw)

        for top_level in data:
            for wishlist in top_level.get("wishlistData", []):
                if wishlist.get("wishlistType") != "WISHLIST":
                    continue

                wl_name = wishlist.get("name", "")
                wl_id = wishlist.get("wishlistId")
                if wl_id is None:
                    continue

                for item in wishlist.get("wishlistItemData", []):
                    pdp_id = item.get("pdpId")
                    if not pdp_id:
                        continue

                    yield AirbnbWishlistItemRecord(
                        pdp_id=str(pdp_id),
                        wishlist_name=wl_name,
                        wishlist_id=int(wl_id),
                        check_in=item.get("checkIn"),
                        check_out=item.get("checkOut"),
                        source=json.dumps(item, default=str),
                    )

    def transform(
        self,
        record: AirbnbWishlistItemRecord,
        task: EtlTask,
    ) -> ThreadRow:
        listing_url = f"https://www.airbnb.com/rooms/{record.pdp_id}"

        page = Page(  # type: ignore[reportCallIssue]
            url=listing_url,
        )

        target = FibreCollection(  # type: ignore[reportCallIssue]
            name=record.wishlist_name,
        )

        published_str = record.check_in or record.check_out
        published = (
            datetime.fromisoformat(published_str).replace(tzinfo=UTC)
            if published_str
            else datetime.now(UTC)
        )

        payload = FibreAddObjectToCollection(  # type: ignore[reportCallIssue]
            object=page,
            target=target,
            published=published,
        )

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview("Airbnb") or "",
            payload=payload.to_dict(),
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=published,
            source=record.source,
        )


declare_interaction(
    InteractionConfig(
        pipe=AirbnbWishlistsPipe,
        memory=MemoryConfig(
            prompt_builder=MediaMemoryPromptBuilder,
            grouper=WindowGrouper,
        ),
    )
)

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import ijson

from context_use.activitystreams.objects import Page
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreAddObjectToCollection,
    FibreCollection,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.airbnb.schemas import PROVIDER
from context_use.providers.airbnb.wishlists.record import AirbnbWishlistItemRecord
from context_use.providers.airbnb.wishlists.schemas import Model
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class AirbnbWishlistsPipe(Pipe[AirbnbWishlistItemRecord]):
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
        stream = storage.open_stream(source_uri)
        try:
            for envelope in self._validated_items(ijson.items(stream, "item"), Model):
                for wishlist in envelope.wishlistData:
                    for item in wishlist.wishlistItemData:
                        yield AirbnbWishlistItemRecord(
                            wishlist_id=wishlist.wishlistId,
                            wishlist_name=wishlist.name,
                            item_id=item.wishlistItemId,
                            pdp_id=item.pdpId,
                            pdp_type=item.pdpType,
                            check_in=item.checkIn,
                            check_out=item.checkOut,
                            source=json.dumps(item.model_dump(), default=str),
                        )
        finally:
            stream.close()

    def transform(
        self,
        record: AirbnbWishlistItemRecord,
        task: EtlTask,
    ) -> ThreadRow:
        listing_url = f"https://www.airbnb.com/rooms/{record.pdp_id}"
        page = Page(name=record.pdp_id, url=listing_url)  # type: ignore[reportCallIssue]
        collection = FibreCollection(name=record.wishlist_name)  # type: ignore[reportCallIssue]

        payload = FibreAddObjectToCollection(  # type: ignore[reportCallIssue]
            object=page,
            target=collection,
        )

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview("Airbnb") or "",
            payload=payload.to_dict(),
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=datetime.now(UTC),
            source=record.source,
        )


declare_interaction(InteractionConfig(pipe=AirbnbWishlistsPipe, memory=None))

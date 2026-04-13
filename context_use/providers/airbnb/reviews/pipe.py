from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import datetime

import ijson

from context_use.activitystreams.objects import Note, Page
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreComment,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.airbnb.reviews.record import AirbnbReviewRecord
from context_use.providers.airbnb.reviews.schemas import Model
from context_use.providers.airbnb.schemas import PROVIDER
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def _parse_timestamp(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


class AirbnbReviewsPipe(Pipe[AirbnbReviewRecord]):
    provider = PROVIDER
    interaction_type = "airbnb_reviews"
    archive_version = 1
    archive_path_pattern = "*/json/reviews.json"
    record_schema = AirbnbReviewRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[AirbnbReviewRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for envelope in self._validated_items(ijson.items(stream, "item"), Model):
                for entry in envelope.reviewsProvided:
                    review = entry.review
                    yield AirbnbReviewRecord(
                        review_id=review.reviewId,
                        reviewer_id=review.reviewerId,
                        comment=review.comment,
                        rating=review.rating,
                        entity_type=review.entityType,
                        entity_id=review.entityId,
                        bookable_id=review.bookableId,
                        created_at=review.createdAt,
                        comment_language=review.commentLanguage,
                        source=json.dumps(entry.model_dump(), default=str),
                    )
        finally:
            stream.close()

    def transform(
        self,
        record: AirbnbReviewRecord,
        task: EtlTask,
    ) -> ThreadRow:
        listing_url = f"https://www.airbnb.com/rooms/{record.bookable_id}"
        note = Note(content=record.comment)  # type: ignore[reportCallIssue]
        listing_page = Page(url=listing_url)  # type: ignore[reportCallIssue]
        published = _parse_timestamp(record.created_at)

        payload = FibreComment(  # type: ignore[reportCallIssue]
            object=note,
            inReplyTo=listing_page,
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


declare_interaction(InteractionConfig(pipe=AirbnbReviewsPipe, memory=None))

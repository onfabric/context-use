"""Instagram stories + reels extraction and transform strategies."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import pandas as pd

from context_use.etl.core.etl import ExtractionStrategy, TransformStrategy
from context_use.etl.core.types import ExtractedBatch
from context_use.etl.models.etl_task import EtlTask
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreCreateObject,
    Image,
    Video,
)
from context_use.etl.providers.instagram.schemas import (
    InstagramMediaItem,
    InstagramMediaRecord,
    InstagramReelsManifest,
    InstagramStoriesManifest,
)
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _infer_media_type(uri: str) -> str:
    """Infer 'Image' or 'Video' from file extension."""
    lower = uri.lower()
    if lower.endswith((".mp4", ".mov", ".avi", ".webm", ".srt")):
        return "Video"
    return "Image"


def _items_to_records(
    items: list[InstagramMediaItem],
    source_file: str,
) -> list[InstagramMediaRecord]:
    """Convert a list of InstagramMediaItem into InstagramMediaRecord instances."""
    records: list[InstagramMediaRecord] = []
    for item in items:
        records.append(
            InstagramMediaRecord(
                uri=item.uri,
                creation_timestamp=item.creation_timestamp,
                title=item.title,
                media_type=_infer_media_type(item.uri),
                source=json.dumps({"file": source_file, "uri": item.uri}),
            )
        )
    return records


# ---------------------------------------------------------------------------
# Stories Extraction
# ---------------------------------------------------------------------------


class InstagramStoriesExtractionStrategy(ExtractionStrategy):
    """Reads ``stories.json`` and yields batches of typed media records."""

    record_schema = InstagramMediaRecord  # type: ignore[reportAssignmentType]

    def extract(
        self,
        task: EtlTask,
        storage: StorageBackend,
    ) -> list[ExtractedBatch[InstagramMediaRecord]]:
        key = task.source_uri

        raw = storage.read(key)
        manifest = InstagramStoriesManifest.model_validate_json(raw)

        records = _items_to_records(manifest.ig_stories, key)
        if not records:
            return []
        return [ExtractedBatch(records=records)]


# ---------------------------------------------------------------------------
# Reels Extraction
# ---------------------------------------------------------------------------


class InstagramReelsExtractionStrategy(ExtractionStrategy):
    """Reads ``reels.json`` and yields batches of typed media records."""

    record_schema = InstagramMediaRecord  # type: ignore[reportAssignmentType]

    def extract(
        self,
        task: EtlTask,
        storage: StorageBackend,
    ) -> list[ExtractedBatch[InstagramMediaRecord]]:
        key = task.source_uri

        raw = storage.read(key)
        manifest = InstagramReelsManifest.model_validate_json(raw)

        # Flatten nested media lists
        all_items: list[InstagramMediaItem] = []
        for entry in manifest.ig_reels_media:
            all_items.extend(entry.media)

        records = _items_to_records(all_items, key)
        if not records:
            return []
        return [ExtractedBatch(records=records)]


# ---------------------------------------------------------------------------
# Shared Transform (stories + reels)
# ---------------------------------------------------------------------------


class _InstagramMediaTransformStrategy(TransformStrategy):
    """Shared transform logic for Instagram media (stories and reels)."""

    record_schema = InstagramMediaRecord  # type: ignore[reportAssignmentType]

    def transform(
        self,
        task: EtlTask,
        batches: list[ExtractedBatch[InstagramMediaRecord]],
    ) -> list[pd.DataFrame]:
        result_batches: list[pd.DataFrame] = []

        for batch in batches:
            rows: list[dict] = []
            for record in batch.records:
                payload = self._build_payload(record, task.provider)
                if payload is None:
                    continue

                asat = datetime.fromtimestamp(float(record.creation_timestamp), tz=UTC)

                unique_key = f"{task.interaction_type}:{payload.unique_key_suffix()}"
                rows.append(
                    {
                        "unique_key": unique_key,
                        "provider": task.provider,
                        "interaction_type": task.interaction_type,
                        "preview": payload.get_preview(task.provider) or "",
                        "payload": payload.to_dict(),
                        "source": record.source,
                        "version": CURRENT_THREAD_PAYLOAD_VERSION,
                        "asat": asat,
                        "asset_uri": (
                            f"{task.archive_id}/{record.uri}" if record.uri else None
                        ),
                    }
                )

            if rows:
                result_batches.append(pd.DataFrame(rows))

        return result_batches

    @staticmethod
    def _build_payload(
        record: InstagramMediaRecord,
        provider: str,
    ) -> FibreCreateObject | None:
        published = datetime.fromtimestamp(float(record.creation_timestamp), tz=UTC)

        if record.media_type == "Video":
            media_obj = Video(
                url=record.uri, name=record.title or None, published=published
            )  # type: ignore[reportCallIssue]
        else:
            media_obj = Image(
                url=record.uri, name=record.title or None, published=published
            )  # type: ignore[reportCallIssue]

        return FibreCreateObject(  # type: ignore[reportCallIssue]
            object=media_obj,
            published=published,
        )


class InstagramStoriesTransformStrategy(_InstagramMediaTransformStrategy):
    """Transform strategy for Instagram stories."""

    pass


class InstagramReelsTransformStrategy(_InstagramMediaTransformStrategy):
    """Transform strategy for Instagram reels."""

    pass

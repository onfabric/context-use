"""Instagram stories + reels extraction and transform strategies."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pandas as pd

from contextuse.core.etl import ExtractionStrategy, TransformStrategy
from contextuse.core.types import TaskMetadata
from contextuse.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreCreateObject,
    Image,
    Video,
)
from contextuse.providers.instagram.schemas import (
    InstagramMediaItem,
    InstagramReelsManifest,
    InstagramStoriesManifest,
)
from contextuse.storage.base import StorageBackend

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
) -> list[dict]:
    """Convert a list of InstagramMediaItem into flat dicts for a DataFrame."""
    records: list[dict] = []
    for item in items:
        records.append(
            {
                "uri": item.uri,
                "creation_timestamp": item.creation_timestamp,
                "title": item.title,
                "media_type": _infer_media_type(item.uri),
                "source": json.dumps(
                    {"file": source_file, "uri": item.uri}
                ),
            }
        )
    return records


# ---------------------------------------------------------------------------
# Stories Extraction
# ---------------------------------------------------------------------------


class InstagramStoriesExtractionStrategy(ExtractionStrategy):
    """Reads ``stories.json`` and yields DataFrames of raw story records."""

    def extract(
        self,
        task: TaskMetadata,
        storage: StorageBackend,
    ) -> list[pd.DataFrame]:
        key = task.filenames[0]

        raw = storage.read(key)
        manifest = InstagramStoriesManifest.model_validate_json(raw)

        records = _items_to_records(manifest.ig_stories, key)
        if not records:
            return []
        return [pd.DataFrame(records)]


# ---------------------------------------------------------------------------
# Reels Extraction
# ---------------------------------------------------------------------------


class InstagramReelsExtractionStrategy(ExtractionStrategy):
    """Reads ``reels.json`` and yields DataFrames of raw reel records."""

    def extract(
        self,
        task: TaskMetadata,
        storage: StorageBackend,
    ) -> list[pd.DataFrame]:
        key = task.filenames[0]

        raw = storage.read(key)
        manifest = InstagramReelsManifest.model_validate_json(raw)

        # Flatten nested media lists
        all_items: list[InstagramMediaItem] = []
        for entry in manifest.ig_reels_media:
            all_items.extend(entry.media)

        records = _items_to_records(all_items, key)
        if not records:
            return []
        return [pd.DataFrame(records)]


# ---------------------------------------------------------------------------
# Shared Transform (stories + reels)
# ---------------------------------------------------------------------------


class _InstagramMediaTransformStrategy(TransformStrategy):
    """Shared transform logic for Instagram media (stories and reels)."""

    def transform(
        self,
        task: TaskMetadata,
        batches: list[pd.DataFrame],
    ) -> list[pd.DataFrame]:
        result_batches: list[pd.DataFrame] = []

        for df in batches:
            rows: list[dict] = []
            for _, record in df.iterrows():
                payload = self._build_payload(record, task.provider)
                if payload is None:
                    continue

                ts = record["creation_timestamp"]
                asat = datetime.fromtimestamp(ts, tz=timezone.utc)

                rows.append(
                    {
                        "unique_key": f"{task.interaction_type}:{payload.unique_key_suffix()}",
                        "provider": task.provider,
                        "interaction_type": task.interaction_type,
                        "preview": payload.get_preview(task.provider) or "",
                        "payload": payload.to_dict(),
                        "source": record.get("source"),
                        "version": CURRENT_THREAD_PAYLOAD_VERSION,
                        "asat": asat,
                        "asset_uri": record.get("uri"),
                    }
                )

            if rows:
                result_batches.append(pd.DataFrame(rows))

        return result_batches

    @staticmethod
    def _build_payload(record: pd.Series, provider: str) -> FibreCreateObject | None:
        media_type = record["media_type"]
        uri = record["uri"]
        title = record.get("title", "")
        ts = record["creation_timestamp"]
        published = datetime.fromtimestamp(ts, tz=timezone.utc)

        if media_type == "Video":
            media_obj = Video(url=uri, name=title or None, published=published)
        else:
            media_obj = Image(url=uri, name=title or None, published=published)

        return FibreCreateObject(
            object=media_obj,
            published=published,
        )


class InstagramStoriesTransformStrategy(_InstagramMediaTransformStrategy):
    """Transform strategy for Instagram stories."""

    pass


class InstagramReelsTransformStrategy(_InstagramMediaTransformStrategy):
    """Transform strategy for Instagram reels."""

    pass


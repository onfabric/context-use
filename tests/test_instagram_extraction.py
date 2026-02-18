"""Tests for Instagram extraction strategies."""

import json
from pathlib import Path

import pytest

from context_use.etl.core.types import ExtractedBatch
from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.etl.providers.instagram.media import (
    InstagramReelsExtractionStrategy,
    InstagramStoriesExtractionStrategy,
)
from context_use.etl.providers.instagram.schemas import InstagramMediaRecord
from context_use.storage.disk import DiskStorage
from tests.conftest import INSTAGRAM_REELS_JSON, INSTAGRAM_STORIES_JSON


@pytest.fixture()
def ig_stories_storage(tmp_path: Path):
    storage = DiskStorage(str(tmp_path / "store"))
    key = "archive/your_instagram_activity/media/stories.json"
    storage.write(key, json.dumps(INSTAGRAM_STORIES_JSON).encode())
    return storage, key


@pytest.fixture()
def ig_reels_storage(tmp_path: Path):
    storage = DiskStorage(str(tmp_path / "store"))
    key = "archive/your_instagram_activity/media/reels.json"
    storage.write(key, json.dumps(INSTAGRAM_REELS_JSON).encode())
    return storage, key


def _make_stories_task(key: str) -> EtlTask:
    return EtlTask(
        archive_id="a1",
        provider="instagram",
        interaction_type="instagram_stories",
        source_uri=key,
        status=EtlTaskStatus.CREATED.value,
    )


def _make_reels_task(key: str) -> EtlTask:
    return EtlTask(
        archive_id="a1",
        provider="instagram",
        interaction_type="instagram_reels",
        source_uri=key,
        status=EtlTaskStatus.CREATED.value,
    )


class TestInstagramStoriesExtraction:
    def test_returns_extracted_batches(self, ig_stories_storage):
        storage, key = ig_stories_storage
        strategy = InstagramStoriesExtractionStrategy()
        task = _make_stories_task(key)

        batches = strategy.extract(task, storage)
        assert len(batches) == 1
        assert isinstance(batches[0], ExtractedBatch)

    def test_records_are_typed(self, ig_stories_storage):
        storage, key = ig_stories_storage
        strategy = InstagramStoriesExtractionStrategy()
        task = _make_stories_task(key)

        batches = strategy.extract(task, storage)
        for record in batches[0].records:
            assert isinstance(record, InstagramMediaRecord)

    def test_record_fields(self, ig_stories_storage):
        storage, key = ig_stories_storage
        strategy = InstagramStoriesExtractionStrategy()
        task = _make_stories_task(key)

        batches = strategy.extract(task, storage)
        record = batches[0].records[0]
        assert record.uri
        assert record.creation_timestamp > 0
        assert record.media_type in ("Image", "Video")
        assert record.source is not None

    def test_row_count(self, ig_stories_storage):
        storage, key = ig_stories_storage
        strategy = InstagramStoriesExtractionStrategy()
        task = _make_stories_task(key)

        batches = strategy.extract(task, storage)
        assert len(batches[0]) == 2  # 2 stories in fixture

    def test_media_type_inference(self, ig_stories_storage):
        storage, key = ig_stories_storage
        strategy = InstagramStoriesExtractionStrategy()
        task = _make_stories_task(key)

        batches = strategy.extract(task, storage)
        types = [r.media_type for r in batches[0].records]
        assert "Video" in types  # .mp4 file
        assert "Image" in types  # .jpg file


class TestInstagramReelsExtraction:
    def test_extracts_and_flattens(self, ig_reels_storage):
        storage, key = ig_reels_storage
        strategy = InstagramReelsExtractionStrategy()
        task = _make_reels_task(key)

        batches = strategy.extract(task, storage)
        assert len(batches) == 1
        assert len(batches[0]) == 1  # 1 reel clip

    def test_reel_is_video(self, ig_reels_storage):
        storage, key = ig_reels_storage
        strategy = InstagramReelsExtractionStrategy()
        task = _make_reels_task(key)

        batches = strategy.extract(task, storage)
        assert batches[0].records[0].media_type == "Video"

    def test_record_schema_declared(self):
        assert InstagramStoriesExtractionStrategy.record_schema is InstagramMediaRecord
        assert InstagramReelsExtractionStrategy.record_schema is InstagramMediaRecord

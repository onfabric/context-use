"""Tests for Instagram extraction strategies."""

import json
from pathlib import Path

import pytest

from context_use.etl.core.types import TaskMetadata
from context_use.etl.providers.instagram.media import (
    InstagramReelsExtractionStrategy,
    InstagramStoriesExtractionStrategy,
)
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


class TestInstagramStoriesExtraction:
    def test_extracts_correct_columns(self, ig_stories_storage):
        storage, key = ig_stories_storage
        strategy = InstagramStoriesExtractionStrategy()
        task = TaskMetadata(
            archive_id="a1",
            etl_task_id="t1",
            provider="instagram",
            interaction_type="instagram_stories",
            filenames=[key],
        )

        batches = strategy.extract(task, storage)
        assert len(batches) == 1
        df = batches[0]
        assert {"uri", "creation_timestamp", "title", "media_type", "source"}.issubset(
            set(df.columns)
        )

    def test_row_count(self, ig_stories_storage):
        storage, key = ig_stories_storage
        strategy = InstagramStoriesExtractionStrategy()
        task = TaskMetadata(
            archive_id="a1",
            etl_task_id="t1",
            provider="instagram",
            interaction_type="instagram_stories",
            filenames=[key],
        )

        batches = strategy.extract(task, storage)
        assert len(batches[0]) == 2  # 2 stories in fixture

    def test_media_type_inference(self, ig_stories_storage):
        storage, key = ig_stories_storage
        strategy = InstagramStoriesExtractionStrategy()
        task = TaskMetadata(
            archive_id="a1",
            etl_task_id="t1",
            provider="instagram",
            interaction_type="instagram_stories",
            filenames=[key],
        )

        batches = strategy.extract(task, storage)
        df = batches[0]
        types = df["media_type"].tolist()
        assert "Video" in types  # .mp4 file
        assert "Image" in types  # .jpg file


class TestInstagramReelsExtraction:
    def test_extracts_and_flattens(self, ig_reels_storage):
        storage, key = ig_reels_storage
        strategy = InstagramReelsExtractionStrategy()
        task = TaskMetadata(
            archive_id="a1",
            etl_task_id="t1",
            provider="instagram",
            interaction_type="instagram_reels",
            filenames=[key],
        )

        batches = strategy.extract(task, storage)
        assert len(batches) == 1
        assert len(batches[0]) == 1  # 1 reel clip

    def test_reel_is_video(self, ig_reels_storage):
        storage, key = ig_reels_storage
        strategy = InstagramReelsExtractionStrategy()
        task = TaskMetadata(
            archive_id="a1",
            etl_task_id="t1",
            provider="instagram",
            interaction_type="instagram_reels",
            filenames=[key],
        )

        batches = strategy.extract(task, storage)
        assert batches[0]["media_type"].iloc[0] == "Video"

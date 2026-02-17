"""Tests for Instagram transform strategies."""

import json
from pathlib import Path

import pytest

from context_use.core.types import TaskMetadata
from context_use.providers.instagram.media import (
    InstagramReelsExtractionStrategy,
    InstagramReelsTransformStrategy,
    InstagramStoriesExtractionStrategy,
    InstagramStoriesTransformStrategy,
)
from context_use.storage.disk import DiskStorage
from tests.conftest import INSTAGRAM_REELS_JSON, INSTAGRAM_STORIES_JSON


@pytest.fixture()
def ig_stories_raw(tmp_path: Path):
    storage = DiskStorage(str(tmp_path / "store"))
    key = "archive/your_instagram_activity/media/stories.json"
    storage.write(key, json.dumps(INSTAGRAM_STORIES_JSON).encode())

    ext = InstagramStoriesExtractionStrategy()
    task = TaskMetadata(
        archive_id="a1",
        etl_task_id="t1",
        provider="instagram",
        interaction_type="instagram_stories",
        filenames=[key],
    )
    return ext.extract(task, storage), task


@pytest.fixture()
def ig_reels_raw(tmp_path: Path):
    storage = DiskStorage(str(tmp_path / "store"))
    key = "archive/your_instagram_activity/media/reels.json"
    storage.write(key, json.dumps(INSTAGRAM_REELS_JSON).encode())

    ext = InstagramReelsExtractionStrategy()
    task = TaskMetadata(
        archive_id="a1",
        etl_task_id="t1",
        provider="instagram",
        interaction_type="instagram_reels",
        filenames=[key],
    )
    return ext.extract(task, storage), task


class TestInstagramStoriesTransform:
    def test_produces_thread_columns(self, ig_stories_raw):
        raw, task = ig_stories_raw
        transform = InstagramStoriesTransformStrategy()
        result = transform.transform(task, raw)

        assert len(result) >= 1
        df = result[0]
        required = {
            "unique_key",
            "provider",
            "interaction_type",
            "preview",
            "payload",
            "version",
            "asat",
            "asset_uri",
        }
        assert required.issubset(set(df.columns))

    def test_payload_is_create(self, ig_stories_raw):
        raw, task = ig_stories_raw
        transform = InstagramStoriesTransformStrategy()
        result = transform.transform(task, raw)
        df = result[0]

        for payload in df["payload"]:
            assert payload["fibre_kind"] == "Create"

    def test_asset_uri_populated(self, ig_stories_raw):
        raw, task = ig_stories_raw
        transform = InstagramStoriesTransformStrategy()
        result = transform.transform(task, raw)
        df = result[0]

        for uri in df["asset_uri"]:
            assert uri is not None
            assert "media/stories/" in uri


class TestInstagramReelsTransform:
    def test_reel_transform(self, ig_reels_raw):
        raw, task = ig_reels_raw
        transform = InstagramReelsTransformStrategy()
        result = transform.transform(task, raw)

        assert len(result) == 1
        df = result[0]
        assert len(df) == 1
        assert df["payload"].iloc[0]["fibre_kind"] == "Create"
        # Reel is video
        assert df["payload"].iloc[0]["object"]["@type"] == "Video"

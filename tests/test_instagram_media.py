from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.etl.core.types import ThreadRow
from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.etl.providers.instagram.media import (
    InstagramReelsPipe,
    InstagramStoriesPipe,
)
from context_use.etl.providers.instagram.schemas import InstagramMediaRecord
from context_use.storage.disk import DiskStorage
from tests.conftest import INSTAGRAM_REELS_JSON, INSTAGRAM_STORIES_JSON

# -- fixtures ----------------------------------------------------------------


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


# -- Stories: extract --------------------------------------------------------


class TestInstagramStoriesPipeExtract:
    """Tests for the Stories extract phase (individual record yielding)."""

    def test_yields_records(self, ig_stories_storage):
        storage, key = ig_stories_storage
        pipe = InstagramStoriesPipe()
        task = _make_stories_task(key)

        records = list(pipe.extract(task, storage))
        assert len(records) >= 1
        assert all(isinstance(r, InstagramMediaRecord) for r in records)

    def test_record_fields(self, ig_stories_storage):
        storage, key = ig_stories_storage
        pipe = InstagramStoriesPipe()
        task = _make_stories_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.uri
        assert record.creation_timestamp > 0
        assert record.media_type in ("Image", "Video")
        assert record.source is not None

    def test_row_count(self, ig_stories_storage):
        """3 stories in fixture."""
        storage, key = ig_stories_storage
        pipe = InstagramStoriesPipe()
        task = _make_stories_task(key)

        records = list(pipe.extract(task, storage))
        assert len(records) == 3

    def test_media_type_inference(self, ig_stories_storage):
        storage, key = ig_stories_storage
        pipe = InstagramStoriesPipe()
        task = _make_stories_task(key)

        records = list(pipe.extract(task, storage))
        types = [r.media_type for r in records]
        assert "Video" in types  # .mp4 file
        assert "Image" in types  # .jpg files

    def test_record_schema_declared(self):
        assert InstagramStoriesPipe.record_schema is InstagramMediaRecord


# -- Stories: transform (via run) --------------------------------------------


class TestInstagramStoriesPipeTransform:
    """Tests for the Stories transform phase (record → ThreadRow)."""

    def test_produces_thread_rows(self, ig_stories_storage):
        storage, key = ig_stories_storage
        pipe = InstagramStoriesPipe()
        task = _make_stories_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) >= 1
        assert all(isinstance(r, ThreadRow) for r in rows)

    def test_thread_row_fields(self, ig_stories_storage):
        storage, key = ig_stories_storage
        pipe = InstagramStoriesPipe()
        task = _make_stories_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.unique_key.startswith("instagram_stories:")
            assert row.provider == "instagram"
            assert row.interaction_type == "instagram_stories"
            assert row.version
            assert row.asat is not None

    def test_payload_is_create(self, ig_stories_storage):
        storage, key = ig_stories_storage
        pipe = InstagramStoriesPipe()
        task = _make_stories_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert isinstance(row.payload, dict)
            assert row.payload["fibre_kind"] == "Create"

    def test_asset_uri_populated(self, ig_stories_storage):
        storage, key = ig_stories_storage
        pipe = InstagramStoriesPipe()
        task = _make_stories_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.asset_uri is not None
            assert row.asset_uri.startswith(f"{task.archive_id}/")
            assert "media/stories/" in row.asset_uri

    def test_previews_non_empty(self, ig_stories_storage):
        storage, key = ig_stories_storage
        pipe = InstagramStoriesPipe()
        task = _make_stories_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.preview, "Preview should not be empty"

    def test_counts_populated(self, ig_stories_storage):
        storage, key = ig_stories_storage
        pipe = InstagramStoriesPipe()
        task = _make_stories_task(key)

        rows = list(pipe.run(task, storage))
        assert pipe.extracted_count == 3
        assert pipe.transformed_count == 3
        assert len(rows) == 3

    def test_class_vars(self):
        assert InstagramStoriesPipe.provider == "instagram"
        assert InstagramStoriesPipe.interaction_type == "instagram_stories"
        assert InstagramStoriesPipe.archive_version == "v1"
        assert (
            InstagramStoriesPipe.archive_path
            == "your_instagram_activity/media/stories.json"
        )


# -- Reels: extract ----------------------------------------------------------


class TestInstagramReelsPipeExtract:
    """Tests for the Reels extract phase (individual record yielding)."""

    def test_extracts_and_flattens(self, ig_reels_storage):
        storage, key = ig_reels_storage
        pipe = InstagramReelsPipe()
        task = _make_reels_task(key)

        records = list(pipe.extract(task, storage))
        assert len(records) == 1  # 1 reel clip

    def test_reel_is_video(self, ig_reels_storage):
        storage, key = ig_reels_storage
        pipe = InstagramReelsPipe()
        task = _make_reels_task(key)

        records = list(pipe.extract(task, storage))
        assert records[0].media_type == "Video"

    def test_record_schema_declared(self):
        assert InstagramReelsPipe.record_schema is InstagramMediaRecord


# -- Reels: transform (via run) ----------------------------------------------


class TestInstagramReelsPipeTransform:
    """Tests for the Reels transform phase (record → ThreadRow)."""

    def test_reel_transform(self, ig_reels_storage):
        storage, key = ig_reels_storage
        pipe = InstagramReelsPipe()
        task = _make_reels_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 1
        assert rows[0].payload["fibre_kind"] == "Create"
        # Reel is video
        assert rows[0].payload["object"]["@type"] == "Video"

    def test_reel_asset_uri(self, ig_reels_storage):
        storage, key = ig_reels_storage
        pipe = InstagramReelsPipe()
        task = _make_reels_task(key)

        rows = list(pipe.run(task, storage))
        assert rows[0].asset_uri is not None
        assert rows[0].asset_uri.startswith(f"{task.archive_id}/")
        assert "media/reels/" in rows[0].asset_uri

    def test_class_vars(self):
        assert InstagramReelsPipe.provider == "instagram"
        assert InstagramReelsPipe.interaction_type == "instagram_reels"
        assert InstagramReelsPipe.archive_version == "v1"
        assert (
            InstagramReelsPipe.archive_path
            == "your_instagram_activity/media/reels.json"
        )

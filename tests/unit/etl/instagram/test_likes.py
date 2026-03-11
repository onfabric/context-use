from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.instagram.likes import (
    InstagramLikedPostsPipe,
    InstagramLikedPostsV0Pipe,
    InstagramStoryLikesPipe,
    InstagramStoryLikesV0Pipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.instagram.conftest import (
    INSTAGRAM_LIKED_POSTS_V0_JSON,
    INSTAGRAM_LIKED_POSTS_V1_JSON,
    INSTAGRAM_STORY_LIKES_V0_JSON,
    INSTAGRAM_STORY_LIKES_V1_JSON,
)

LIKED_POSTS_ARCHIVE_PATH = "your_instagram_activity/likes/liked_posts.json"
STORY_LIKES_ARCHIVE_PATH = "your_instagram_activity/story_interactions/story_likes.json"


class TestInstagramLikedPostsV0Pipe(PipeTestKit):
    pipe_class = InstagramLikedPostsV0Pipe
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{LIKED_POSTS_ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_LIKED_POSTS_V0_JSON).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.title == "synthetic_foodblog"
        assert record.href == "https://www.instagram.com/reel/XXXXXXXXXXX/"
        assert record.timestamp == 1770775983
        assert record.source is not None

    def test_payload_is_like(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "Reaction"
            assert row.payload["type"] == "Like"

    def test_payload_object_is_post(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            obj = row.payload["object"]
            assert obj["type"] == "Note"  # FibrePost extends Note
            assert obj["fibreKind"] == "Post"

    def test_payload_has_attributed_to(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        attr = rows[0].payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "synthetic_foodblog"

    def test_payload_has_post_url(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        obj = rows[0].payload["object"]
        assert "url" in obj
        assert "XXXXXXXXXXX" in obj["url"]

    def test_preview_includes_liked(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        preview = rows[0].preview
        assert "Liked" in preview
        assert "synthetic_foodblog" in preview
        assert "instagram" in preview.lower()

    def test_asat_from_timestamp(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert rows[0].asat.year >= 2026

    def test_interaction_type(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.interaction_type == "instagram_liked_posts"


class TestInstagramLikedPostsV1Pipe(PipeTestKit):
    pipe_class = InstagramLikedPostsPipe
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{LIKED_POSTS_ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_LIKED_POSTS_V1_JSON).encode())
        return storage, key

    def test_record_fields_with_owner(self, pipe_fixture):
        """First v1 record has an Owner dict → title should be extracted."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.title == "synthetic_foodblog"
        assert record.href == "https://www.instagram.com/reel/XXXXXXXXXXX/"
        assert record.timestamp == 1770775983
        assert record.source is not None

    def test_record_fields_second(self, pipe_fixture):
        """Second v1 record also has Owner → title should be extracted."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[1]
        assert record.title == "synthetic_traveler"
        assert record.href == "https://www.instagram.com/p/YYYYYYYYYYY/"
        assert record.timestamp == 1770683481

    def test_payload_is_like(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "Reaction"
            assert row.payload["type"] == "Like"

    def test_payload_object_is_post_with_url(self, pipe_fixture):
        """V1 data has a post URL → post object should carry url."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        obj = rows[0].payload["object"]
        assert obj["type"] == "Note"  # FibrePost extends Note
        assert obj["fibreKind"] == "Post"
        assert obj["url"] == "https://www.instagram.com/reel/XXXXXXXXXXX/"

    def test_payload_has_attributed_to_from_owner(self, pipe_fixture):
        """Owner dict → attributedTo should be a Profile with username."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        attr = rows[0].payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "synthetic_foodblog"

    def test_preview_includes_liked(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        preview = rows[0].preview
        assert "Liked" in preview
        assert "synthetic_foodblog" in preview

    def test_interaction_type(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.interaction_type == "instagram_liked_posts"


class TestInstagramStoryLikesV0Pipe(PipeTestKit):
    pipe_class = InstagramStoryLikesV0Pipe
    expected_extract_count = 1
    expected_transform_count = 1

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{STORY_LIKES_ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_STORY_LIKES_V0_JSON).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.title == "synthetic_photographer"
        assert record.href is None  # story likes have no href
        assert record.timestamp == 1771028852

    def test_payload_is_like(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "Reaction"
            assert row.payload["type"] == "Like"

    def test_payload_object_is_post_without_url(self, pipe_fixture):
        """Story likes have no URL on the post object."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        obj = rows[0].payload["object"]
        assert obj["type"] == "Note"
        assert obj["fibreKind"] == "Post"
        assert "url" not in obj

    def test_payload_has_attributed_to(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        attr = rows[0].payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "synthetic_photographer"

    def test_preview_includes_liked(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        preview = rows[0].preview
        assert "Liked" in preview
        assert "synthetic_photographer" in preview

    def test_interaction_type(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.interaction_type == "instagram_story_likes"


class TestInstagramStoryLikesV1Pipe(PipeTestKit):
    pipe_class = InstagramStoryLikesPipe
    expected_extract_count = 1
    expected_transform_count = 1

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{STORY_LIKES_ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_STORY_LIKES_V1_JSON).encode())
        return storage, key

    def test_record_fields_with_owner(self, pipe_fixture):
        """V1 story like has Owner dict → title should be extracted."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.title == "synthetic_photographer"
        assert record.href is None  # story likes still have no URL
        assert record.timestamp == 1771028852
        assert record.source is not None

    def test_payload_is_like(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "Reaction"
            assert row.payload["type"] == "Like"

    def test_payload_object_is_post_without_url(self, pipe_fixture):
        """Story likes still have no URL on the post object in v1."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        obj = rows[0].payload["object"]
        assert obj["type"] == "Note"
        assert obj["fibreKind"] == "Post"
        assert "url" not in obj

    def test_payload_has_attributed_to_from_owner(self, pipe_fixture):
        """Owner dict → attributedTo should be a Profile with username."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        attr = rows[0].payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "synthetic_photographer"

    def test_preview_includes_liked(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        preview = rows[0].preview
        assert "Liked" in preview
        assert "synthetic_photographer" in preview

    def test_interaction_type(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.interaction_type == "instagram_story_likes"

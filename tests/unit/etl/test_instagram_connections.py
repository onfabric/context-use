import json
from pathlib import Path

import pytest

from context_use.providers.instagram.connections import (
    InstagramFollowersPipe,
    InstagramFollowingPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import (
    INSTAGRAM_FOLLOWERS_JSON,
    INSTAGRAM_FOLLOWING_JSON,
)

FOLLOWERS_ARCHIVE_PATH = "connections/followers_and_following/followers_1.json"
FOLLOWING_ARCHIVE_PATH = "connections/followers_and_following/following.json"


# ---------------------------------------------------------------------------
# Followers tests
# ---------------------------------------------------------------------------


class TestInstagramFollowersPipe(PipeTestKit):
    pipe_class = InstagramFollowersPipe
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{FOLLOWERS_ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_FOLLOWERS_JSON).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.username == "synthetic_follower_1"
        assert record.profile_url == "https://www.instagram.com/synthetic_follower_1"
        assert record.timestamp == 1768003156
        assert record.source is not None

    def test_payload_is_followed_by(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "FollowedBy"
            assert row.payload["type"] == "Follow"

    def test_payload_actor_is_person(self, pipe_fixture):
        """FibreFollowedBy uses Person (not Profile) for the actor."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        actor = rows[0].payload["actor"]
        assert actor["type"] == "Person"
        assert actor["name"] == "synthetic_follower_1"
        assert "instagram.com/synthetic_follower_1" in actor["url"]

    def test_preview_includes_followed_by(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        preview = rows[0].preview
        assert "Followed by" in preview
        assert "synthetic_follower_1" in preview
        assert "instagram" in preview.lower()

    def test_asat_from_timestamp(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert rows[0].asat.year >= 2025

    def test_interaction_type(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.interaction_type == "instagram_followers"

    def test_glob_pattern_has_wildcard(self):
        """Confirm the glob pattern matches followers_1.json, followers_2.json, etc."""
        assert "*" in InstagramFollowersPipe.archive_path_pattern


# ---------------------------------------------------------------------------
# Following tests
# ---------------------------------------------------------------------------


class TestInstagramFollowingPipe(PipeTestKit):
    pipe_class = InstagramFollowingPipe
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{FOLLOWING_ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_FOLLOWING_JSON).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.username == "synthetic_foodblog"
        assert record.profile_url == "https://www.instagram.com/_u/synthetic_foodblog"
        assert record.timestamp == 1770897717
        assert record.source is not None

    def test_payload_is_following(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "Following"
            assert row.payload["type"] == "Follow"

    def test_payload_object_is_profile(self, pipe_fixture):
        """FibreFollowing uses Profile (not Person) for the object."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        obj = rows[0].payload["object"]
        assert obj["type"] == "Profile"
        assert obj["name"] == "synthetic_foodblog"
        assert "instagram.com" in obj["url"]

    def test_preview_includes_following(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        preview = rows[0].preview
        assert "Following" in preview
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
            assert row.interaction_type == "instagram_following"

    def test_username_from_title(self, pipe_fixture):
        """Username should come from the ``title`` field, not parsed from href."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        # title is "synthetic_foodblog", href has "_u/synthetic_foodblog"
        assert records[0].username == "synthetic_foodblog"

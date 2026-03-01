from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.instagram.connections import (
    InstagramFollowersPipe,
    InstagramFollowingPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import INSTAGRAM_FOLLOWERS_JSON, INSTAGRAM_FOLLOWING_JSON


class TestInstagramFollowersPipe(PipeTestKit):
    pipe_class = InstagramFollowersPipe
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/connections/followers_and_following/followers_1.json"
        storage.write(key, json.dumps(INSTAGRAM_FOLLOWERS_JSON).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.username == "synthetic_follower_1"
        assert "instagram.com" in record.profile_url
        assert record.timestamp > 0
        assert record.source is not None

    def test_username_extracted_from_href(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        usernames = [r.username for r in records]
        assert usernames == ["synthetic_follower_1", "synthetic_follower_2"]

    def test_payload_is_follow(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "Follow"

    def test_follower_is_inbound(self, pipe_fixture):
        """Followers are inbound — the actor is the follower profile."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload.get("actor") is not None
            assert row.payload.get("object") is None

    def test_preview_says_followed_by(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert rows[0].preview.startswith("Followed by synthetic_follower_1")


class TestInstagramFollowingPipe(PipeTestKit):
    pipe_class = InstagramFollowingPipe
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/connections/followers_and_following/following.json"
        storage.write(key, json.dumps(INSTAGRAM_FOLLOWING_JSON).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.username == "synthetic_foodblog"
        assert "instagram.com" in record.profile_url
        assert record.timestamp > 0
        assert record.source is not None

    def test_username_extracted_from_href(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        usernames = [r.username for r in records]
        assert usernames == ["synthetic_foodblog", "synthetic_photographer"]

    def test_payload_is_follow(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "Follow"

    def test_following_is_outbound(self, pipe_fixture):
        """Following is outbound — the object is the followed profile."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload.get("object") is not None
            assert row.payload.get("actor") is None

    def test_preview_says_followed(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert rows[0].preview.startswith("Followed synthetic_foodblog")

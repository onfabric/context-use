from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.instagram.posts_viewed import (
    InstagramPostsViewedPipe,
    InstagramPostsViewedV0Pipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.instagram.conftest import (
    INSTAGRAM_POSTS_VIEWED_V0_JSON,
    INSTAGRAM_POSTS_VIEWED_V1_JSON,
)

ARCHIVE_PATH = "ads_information/ads_and_topics/posts_viewed.json"


class TestInstagramPostsViewedV0Pipe(PipeTestKit):
    pipe_class = InstagramPostsViewedV0Pipe
    expected_extract_count = 3
    expected_transform_count = 3

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_POSTS_VIEWED_V0_JSON).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.author == "synthetic_foodie"
        assert record.timestamp == 1743840091
        assert record.post_url is None  # v0 has no URL
        assert record.source is not None

    def test_payload_is_view(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "View"
            assert row.payload["type"] == "View"

    def test_payload_object_is_post(self, pipe_fixture):
        """Object should be a FibrePost (type=Note, fibreKind=Post)."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            obj = row.payload["object"]
            assert obj["type"] == "Note"  # FibrePost extends Note
            assert obj["fibreKind"] == "Post"

    def test_payload_has_attributed_to_profile(self, pipe_fixture):
        """Author should appear as attributedTo Profile on the post."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        row = rows[0]
        attr = row.payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "synthetic_foodie"
        assert attr["url"] == "https://www.instagram.com/synthetic_foodie"

    def test_preview_includes_post_and_author(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        preview = rows[0].preview
        assert "Viewed post" in preview
        assert "synthetic_foodie" in preview
        assert "instagram" in preview.lower()

    def test_asat_from_timestamp(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        # First record has timestamp 1743840091
        assert rows[0].asat.year >= 2025

    def test_interaction_type(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.interaction_type == "instagram_posts_viewed"


class TestInstagramPostsViewedV1Pipe(PipeTestKit):
    pipe_class = InstagramPostsViewedPipe
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_POSTS_VIEWED_V1_JSON).encode())
        return storage, key

    def test_record_fields_with_owner(self, pipe_fixture):
        """First v1 record has an Owner dict → author should be extracted."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.author == "synthetic_artist"
        assert record.post_url == "https://www.instagram.com/p/SYNTHETIC_POST_1/"
        assert record.timestamp == 1771848416
        assert record.source is not None

    def test_record_fields_without_owner(self, pipe_fixture):
        """Second v1 record has no Owner dict → author should be None."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[1]
        assert record.author is None
        assert record.post_url == "https://www.instagram.com/p/SYNTHETIC_POST_2/"
        assert record.timestamp == 1771762100

    def test_payload_is_view(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "View"
            assert row.payload["type"] == "View"

    def test_payload_object_is_post_with_url(self, pipe_fixture):
        """V1 data has a post URL → post object should carry url."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        obj = rows[0].payload["object"]
        assert obj["type"] == "Note"  # FibrePost extends Note
        assert obj["fibreKind"] == "Post"
        assert obj["url"] == "https://www.instagram.com/p/SYNTHETIC_POST_1/"

    def test_payload_has_attributed_to_from_owner(self, pipe_fixture):
        """First record has Owner → attributedTo should be a Profile."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        attr = rows[0].payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "synthetic_artist"
        assert attr["url"] == "https://www.instagram.com/synthetic_artist"

    def test_payload_no_attributed_to_when_no_owner(self, pipe_fixture):
        """Second record has no Owner → no attributedTo on the post."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert "attributedTo" not in rows[1].payload["object"]

    def test_preview_includes_url(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        # Second record has no author, preview should include the URL
        preview = rows[1].preview
        assert "Viewed post" in preview
        assert "SYNTHETIC_POST_2" in preview

    def test_interaction_type(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.interaction_type == "instagram_posts_viewed"

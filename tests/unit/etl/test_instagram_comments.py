from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.instagram.comments import (
    InstagramCommentPostsPipe,
    InstagramCommentReelsPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import (
    INSTAGRAM_POST_COMMENTS_JSON,
    INSTAGRAM_REELS_COMMENTS_JSON,
)

POST_COMMENTS_ARCHIVE_PATH = "your_instagram_activity/comments/post_comments_1.json"
REELS_COMMENTS_ARCHIVE_PATH = "your_instagram_activity/comments/reels_comments.json"


# ---------------------------------------------------------------------------
# Post comments tests
# ---------------------------------------------------------------------------


class TestInstagramCommentPostsPipe(PipeTestKit):
    pipe_class = InstagramCommentPostsPipe
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{POST_COMMENTS_ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_POST_COMMENTS_JSON).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.comment == "This looks amazing!"
        assert record.media_owner == "synthetic_foodblog"
        assert record.timestamp == 1765415135
        assert record.source is not None

    def test_payload_is_comment(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "Comment"
            assert row.payload["type"] == "Create"  # FibreComment extends Create

    def test_payload_object_is_note(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            obj = row.payload["object"]
            assert obj["type"] == "Note"
            assert obj["content"]

    def test_payload_has_in_reply_to(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        irt = rows[0].payload["inReplyTo"]
        assert irt["type"] == "Note"  # FibrePost extends Note
        assert irt["fibreKind"] == "Post"
        assert irt["attributedTo"]["type"] == "Profile"
        assert irt["attributedTo"]["name"] == "synthetic_foodblog"

    def test_comment_content(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert rows[0].payload["object"]["content"] == "This looks amazing!"
        assert rows[1].payload["object"]["content"] == "Great photo, love the lighting"

    def test_preview_includes_comment_text(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        preview = rows[0].preview
        assert "Commented" in preview
        assert "This looks amazing!" in preview
        assert "synthetic_foodblog" in preview

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
            assert row.interaction_type == "instagram_comments_posts"

    def test_skips_entries_with_no_comment(self, tmp_path: Path):
        """Entries where Comment value is empty should be skipped."""
        data = [
            {
                "string_map_data": {
                    "Comment": {"value": ""},
                    "Media Owner": {"value": "someone"},
                    "Time": {"timestamp": 1765415135},
                }
            },
            {
                "string_map_data": {
                    "Comment": {"value": "Valid comment"},
                    "Media Owner": {"value": "someone"},
                    "Time": {"timestamp": 1765415136},
                }
            },
        ]
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{POST_COMMENTS_ARCHIVE_PATH}"
        storage.write(key, json.dumps(data).encode())
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        assert len(records) == 1
        assert records[0].comment == "Valid comment"


# ---------------------------------------------------------------------------
# Reels comments tests
# ---------------------------------------------------------------------------


class TestInstagramCommentReelsPipe(PipeTestKit):
    pipe_class = InstagramCommentReelsPipe
    expected_extract_count = 1
    expected_transform_count = 1

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{REELS_COMMENTS_ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_REELS_COMMENTS_JSON).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.comment == "This reel is so funny!"
        assert record.media_owner == "synthetic_comedian"
        assert record.timestamp == 1766000000

    def test_payload_is_comment(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "Comment"
            assert row.payload["type"] == "Create"

    def test_payload_object_content(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert rows[0].payload["object"]["content"] == "This reel is so funny!"

    def test_interaction_type(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.interaction_type == "instagram_comments_reels"

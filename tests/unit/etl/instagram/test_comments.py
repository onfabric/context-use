from __future__ import annotations

import json
from pathlib import Path

from context_use.providers.instagram.comments import (
    InstagramCommentPostsPipe,
    InstagramCommentReelsPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.instagram.conftest import (
    INSTAGRAM_POST_COMMENTS_JSON,
    INSTAGRAM_REELS_COMMENTS_JSON,
)

POST_COMMENTS_ARCHIVE_PATH = "your_instagram_activity/comments/post_comments_1.json"


class TestInstagramCommentPostsPipe(PipeTestKit):
    pipe_class = InstagramCommentPostsPipe
    expected_extract_count = 2
    expected_transform_count = 2
    expected_fibre_kind = "Comment"
    fixture_data = INSTAGRAM_POST_COMMENTS_JSON
    fixture_key = f"archive/{POST_COMMENTS_ARCHIVE_PATH}"

    def test_non_array_produces_no_rows(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{POST_COMMENTS_ARCHIVE_PATH}"
        storage.write(key, b'{"not": "an array"}')
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 0

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.comment == "This looks amazing!"
        assert record.media_owner == "synthetic_foodblog"
        assert record.timestamp == 1765415135
        assert record.source is not None

    def test_payload_object_is_note(self, transformed_rows):
        for row in transformed_rows:
            obj = row.payload["object"]
            assert obj["type"] == "Note"
            assert obj["content"]

    def test_payload_has_in_reply_to(self, transformed_rows):
        irt = transformed_rows[0].payload["inReplyTo"]
        assert irt["type"] == "Note"
        assert irt["fibreKind"] == "Post"
        assert irt["attributedTo"]["type"] == "Profile"
        assert irt["attributedTo"]["name"] == "synthetic_foodblog"

    def test_comment_content(self, transformed_rows):
        assert transformed_rows[0].payload["object"]["content"] == "This looks amazing!"
        assert (
            transformed_rows[1].payload["object"]["content"]
            == "Great photo, love the lighting"
        )

    def test_preview_includes_comment_text(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Commented" in preview
        assert "This looks amazing!" in preview
        assert "synthetic_foodblog" in preview

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


class TestInstagramCommentReelsPipe(PipeTestKit):
    pipe_class = InstagramCommentReelsPipe
    expected_extract_count = 1
    expected_transform_count = 1
    expected_fibre_kind = "Comment"
    fixture_data = INSTAGRAM_REELS_COMMENTS_JSON
    fixture_key = "archive/your_instagram_activity/comments/reels_comments.json"

    def test_file_schema_gates_missing_key(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/your_instagram_activity/comments/reels_comments.json"
        storage.write(key, b'{"wrong_key": []}')
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 0
        assert pipe.error_count == 1

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.comment == "This reel is so funny!"
        assert record.media_owner == "synthetic_comedian"
        assert record.timestamp == 1766000000

    def test_payload_object_content(self, transformed_rows):
        assert (
            transformed_rows[0].payload["object"]["content"] == "This reel is so funny!"
        )

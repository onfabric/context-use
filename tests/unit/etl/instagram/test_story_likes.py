from __future__ import annotations

from pathlib import Path

from context_use.providers.instagram.story_likes.pipe import (
    InstagramStoryLikesV0Pipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import AttributedToProfileMixin, PipeTestKit, PostObjectMixin
from tests.unit.etl.instagram.conftest import INSTAGRAM_STORY_LIKES_V0_JSON


class TestInstagramStoryLikesV0Pipe(
    PostObjectMixin, AttributedToProfileMixin, PipeTestKit
):
    pipe_class = InstagramStoryLikesV0Pipe
    expected_extract_count = 1
    expected_transform_count = 1
    fixture_data = INSTAGRAM_STORY_LIKES_V0_JSON
    fixture_key = "archive/your_instagram_activity/story_interactions/story_likes.json"
    expected_fibre_kind = "Reaction"

    def test_file_schema_gates_missing_key(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        assert self.fixture_key is not None
        key = self.fixture_key
        storage.write(key, b'{"wrong_key": []}')
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 0
        assert pipe.error_count == 1

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.title == "synthetic_photographer"
        assert record.href is None
        assert record.timestamp == 1771028852

    def test_payload_object_has_no_url(self, transformed_rows):
        assert "url" not in transformed_rows[0].payload["object"]

    def test_attribution_name(self, transformed_rows):
        assert (
            transformed_rows[0].payload["object"]["attributedTo"]["name"]
            == "synthetic_photographer"
        )

    def test_preview_includes_liked(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Liked" in preview
        assert "synthetic_photographer" in preview

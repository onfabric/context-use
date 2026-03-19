from __future__ import annotations

from pathlib import Path

from context_use.providers.instagram.story_likes.pipe import (
    InstagramStoryLikesPipe,
    InstagramStoryLikesV0Pipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import AttributedToProfileMixin, PipeTestKit, PostObjectMixin
from tests.unit.etl.instagram.conftest import (
    INSTAGRAM_STORY_LIKES_V0_JSON,
    INSTAGRAM_STORY_LIKES_V1_JSON,
)


class TestInstagramStoryLikesV0Pipe(
    PostObjectMixin, AttributedToProfileMixin, PipeTestKit
):
    pipe_class = InstagramStoryLikesV0Pipe
    expected_extract_count = 2
    expected_transform_count = 2
    fixture_data = INSTAGRAM_STORY_LIKES_V0_JSON
    fixture_key = "archive/your_instagram_activity/story_interactions/story_likes.json"
    expected_fibre_kind = "Reaction"

    def test_file_schema_gates_missing_key(self, tmp_path: Path) -> None:
        storage = DiskStorage(str(tmp_path / "store"))
        assert self.fixture_key is not None
        key = self.fixture_key
        storage.write(key, b'{"wrong_key": []}')
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 0
        assert pipe.error_count == 1

    def test_record_fields(self, extracted_records) -> None:
        record = extracted_records[0]
        assert record.title == "synthetic_photographer"
        assert record.href is None
        assert record.timestamp == 1771028852

    def test_record_fields_second(self, extracted_records) -> None:
        record = extracted_records[1]
        assert record.title == "synthetic_traveler"
        assert record.href is None
        assert record.timestamp == 1770912145

    def test_payload_object_has_no_url(self, transformed_rows) -> None:
        assert "url" not in transformed_rows[0].payload["object"]

    def test_attribution_name(self, transformed_rows) -> None:
        assert (
            transformed_rows[0].payload["object"]["attributedTo"]["name"]
            == "synthetic_photographer"
        )

    def test_preview_includes_liked(self, transformed_rows) -> None:
        preview = transformed_rows[0].preview
        assert "Liked" in preview
        assert "synthetic_photographer" in preview


class TestInstagramStoryLikesV1Pipe(
    PostObjectMixin, AttributedToProfileMixin, PipeTestKit
):
    pipe_class = InstagramStoryLikesPipe
    expected_extract_count = 2
    expected_transform_count = 2
    fixture_data = INSTAGRAM_STORY_LIKES_V1_JSON
    fixture_key = "archive/your_instagram_activity/story_interactions/story_likes.json"
    expected_fibre_kind = "Reaction"

    def test_non_array_produces_no_rows(self, tmp_path: Path) -> None:
        storage = DiskStorage(str(tmp_path / "store"))
        assert self.fixture_key is not None
        key = self.fixture_key
        storage.write(key, b'{"not": "an array"}')
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 0

    def test_record_fields_with_owner(self, extracted_records) -> None:
        record = extracted_records[0]
        assert record.title == "synthetic_photographer"
        assert (
            record.href
            == "https://www.instagram.com/stories/synthetic_photographer/1234567890123456789"
        )
        assert record.timestamp == 1771028852
        assert record.source is not None

    def test_record_fields_second(self, extracted_records) -> None:
        record = extracted_records[1]
        assert record.title == "synthetic_traveler"
        assert (
            record.href
            == "https://www.instagram.com/stories/synthetic_traveler/9876543210987654321"
        )
        assert record.timestamp == 1770912145

    def test_payload_object_url(self, transformed_rows) -> None:
        assert (
            transformed_rows[0].payload["object"]["url"]
            == "https://www.instagram.com/stories/synthetic_photographer/1234567890123456789"
        )

    def test_attribution_name(self, transformed_rows) -> None:
        assert (
            transformed_rows[0].payload["object"]["attributedTo"]["name"]
            == "synthetic_photographer"
        )

    def test_preview_includes_liked(self, transformed_rows) -> None:
        preview = transformed_rows[0].preview
        assert "Liked" in preview
        assert "synthetic_photographer" in preview

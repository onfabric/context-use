from __future__ import annotations

from datetime import UTC, datetime
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
    snapshot_cases = [
        (
            {
                "story_activities_story_likes": [
                    {
                        "title": "snapshot_user",
                        "string_list_data": [{"timestamp": 1771028852}],
                    }
                ]
            },
            {
                "unique_key": "45547f41730aba7c",
                "preview": "Liked post by snapshot_user on instagram",
                "asat": datetime(2026, 2, 14, 0, 27, 32, tzinfo=UTC),
                "payload": {
                    "type": "Like",
                    "published": "2026-02-14T00:27:32Z",
                    "object": {
                        "type": "Note",
                        "attributedTo": {
                            "type": "Profile",
                            "name": "snapshot_user",
                        },
                        "fibreKind": "Post",
                    },
                    "fibreKind": "Reaction",
                },
            },
        ),
    ]

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
    snapshot_cases = [
        (
            [
                {
                    "timestamp": 1771028852,
                    "media": [],
                    "label_values": [
                        {
                            "label": "URL",
                            "value": "https://www.instagram.com/stories/snapshot_user/1234567890123456789",
                            "href": "https://www.instagram.com/stories/snapshot_user/1234567890123456789",
                        },
                        {
                            "dict": [
                                {
                                    "dict": [
                                        {"label": "URL", "value": ""},
                                        {"label": "Name", "value": "Snapshot User"},
                                        {
                                            "label": "Username",
                                            "value": "snapshot_user",
                                        },
                                    ],
                                    "title": "",
                                }
                            ],
                            "title": "Owner",
                        },
                    ],
                    "fbid": "18079916561048999",
                }
            ],
            {
                "unique_key": "750ef1e77f6a5361",
                "preview": "Liked post by snapshot_user on instagram",
                "asat": datetime(2026, 2, 14, 0, 27, 32, tzinfo=UTC),
                "payload": {
                    "type": "Like",
                    "published": "2026-02-14T00:27:32Z",
                    "object": {
                        "type": "Note",
                        "attributedTo": {
                            "type": "Profile",
                            "name": "snapshot_user",
                        },
                        "url": "https://www.instagram.com/stories/snapshot_user/1234567890123456789",
                        "fibreKind": "Post",
                    },
                    "fibreKind": "Reaction",
                },
            },
        ),
    ]

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

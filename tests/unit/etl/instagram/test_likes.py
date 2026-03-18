from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from context_use.providers.instagram.likes.pipe import (
    InstagramLikedPostsPipe,
    InstagramLikedPostsV0Pipe,
    InstagramStoryLikesPipe,
    InstagramStoryLikesV0Pipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import AttributedToProfileMixin, PipeTestKit, PostObjectMixin
from tests.unit.etl.instagram.conftest import (
    INSTAGRAM_LIKED_POSTS_V0_JSON,
    INSTAGRAM_LIKED_POSTS_V1_JSON,
    INSTAGRAM_STORY_LIKES_V0_JSON,
    INSTAGRAM_STORY_LIKES_V1_JSON,
)


class TestInstagramLikedPostsV0Pipe(
    PostObjectMixin, AttributedToProfileMixin, PipeTestKit
):
    pipe_class = InstagramLikedPostsV0Pipe
    expected_extract_count = 2
    expected_transform_count = 2
    fixture_data = INSTAGRAM_LIKED_POSTS_V0_JSON
    fixture_key = "archive/your_instagram_activity/likes/liked_posts.json"
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
        assert record.title == "synthetic_foodblog"
        assert record.href == "https://www.instagram.com/reel/XXXXXXXXXXX/"
        assert record.timestamp == 1770775983
        assert record.source is not None

    def test_attribution_name(self, transformed_rows):
        assert (
            transformed_rows[0].payload["object"]["attributedTo"]["name"]
            == "synthetic_foodblog"
        )

    def test_payload_has_post_url(self, transformed_rows):
        obj = transformed_rows[0].payload["object"]
        assert "url" in obj
        assert "XXXXXXXXXXX" in obj["url"]

    def test_preview_includes_liked(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Liked" in preview
        assert "synthetic_foodblog" in preview
        assert "instagram" in preview.lower()


class TestInstagramLikedPostsV1Pipe(
    PostObjectMixin, AttributedToProfileMixin, PipeTestKit
):
    pipe_class = InstagramLikedPostsPipe
    expected_extract_count = 2
    expected_transform_count = 2
    fixture_data = INSTAGRAM_LIKED_POSTS_V1_JSON
    fixture_key = "archive/your_instagram_activity/likes/liked_posts.json"
    expected_fibre_kind = "Reaction"

    def test_non_array_produces_no_rows(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        assert self.fixture_key is not None
        key = self.fixture_key
        storage.write(key, b'{"not": "an array"}')
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 0

    def test_record_fields_with_owner(self, extracted_records):
        record = extracted_records[0]
        assert record.title == "synthetic_foodblog"
        assert record.href == "https://www.instagram.com/reel/XXXXXXXXXXX/"
        assert record.timestamp == 1770775983
        assert record.source is not None

    def test_record_fields_second(self, extracted_records):
        record = extracted_records[1]
        assert record.title == "synthetic_traveler"
        assert record.href == "https://www.instagram.com/p/YYYYYYYYYYY/"
        assert record.timestamp == 1770683481

    def test_payload_object_url(self, transformed_rows):
        assert (
            transformed_rows[0].payload["object"]["url"]
            == "https://www.instagram.com/reel/XXXXXXXXXXX/"
        )

    def test_attribution_name(self, transformed_rows):
        assert (
            transformed_rows[0].payload["object"]["attributedTo"]["name"]
            == "synthetic_foodblog"
        )

    def test_preview_includes_liked(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Liked" in preview
        assert "synthetic_foodblog" in preview


class TestInstagramStoryLikesV0Pipe(
    PostObjectMixin, AttributedToProfileMixin, PipeTestKit
):
    pipe_class = InstagramStoryLikesV0Pipe
    expected_extract_count = 3
    expected_transform_count = 3
    fixture_data = INSTAGRAM_STORY_LIKES_V0_JSON
    fixture_key = "archive/your_instagram_activity/story_interactions/story_likes.json"
    expected_fibre_kind = "Reaction"
    snapshot_cases = [
        (
            {
                "story_activities_story_likes": [
                    {
                        "title": "synthetic_photographer",
                        "string_list_data": [{"timestamp": 1771028852}],
                    }
                ]
            },
            {
                "unique_key": "94963cc154c4324e",
                "preview": "Liked post by synthetic_photographer on instagram",
                "asat": datetime(2026, 2, 14, 0, 27, 32, tzinfo=UTC),
                "payload": {
                    "type": "Like",
                    "published": "2026-02-14T00:27:32Z",
                    "object": {
                        "type": "Note",
                        "attributedTo": {
                            "type": "Profile",
                            "name": "synthetic_photographer",
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

    def test_record_fields_first(self, extracted_records) -> None:
        record = extracted_records[0]
        assert record.title == "synthetic_photographer"
        assert record.href is None
        assert record.timestamp == 1771028852
        assert record.source is not None

    def test_record_fields_second(self, extracted_records) -> None:
        record = extracted_records[1]
        assert record.title == "synthetic_traveler"
        assert record.href is None
        assert record.timestamp == 1771115252

    def test_record_fields_third(self, extracted_records) -> None:
        record = extracted_records[2]
        assert record.title == "synthetic_artist"
        assert record.timestamp == 1771201652

    def test_payload_object_has_no_url(self, transformed_rows) -> None:
        for row in transformed_rows:
            assert "url" not in row.payload["object"]

    def test_attribution_names(self, transformed_rows) -> None:
        names = [
            row.payload["object"]["attributedTo"]["name"] for row in transformed_rows
        ]
        assert names == [
            "synthetic_photographer",
            "synthetic_traveler",
            "synthetic_artist",
        ]

    def test_preview_includes_liked(self, transformed_rows) -> None:
        for row in transformed_rows:
            assert "Liked" in row.preview
            assert "instagram" in row.preview.lower()
        assert "synthetic_photographer" in transformed_rows[0].preview
        assert "synthetic_traveler" in transformed_rows[1].preview


class TestInstagramStoryLikesPipe(
    PostObjectMixin, AttributedToProfileMixin, PipeTestKit
):
    pipe_class = InstagramStoryLikesPipe
    expected_extract_count = 3
    expected_transform_count = 3
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
                            "value": "https://www.instagram.com/stories/synthetic_photographer/3800000000000000001",
                            "href": "https://www.instagram.com/stories/synthetic_photographer/3800000000000000001",
                        },
                        {
                            "dict": [
                                {
                                    "dict": [
                                        {"label": "URL", "value": ""},
                                        {
                                            "label": "Name",
                                            "value": "Synthetic Photographer",
                                        },
                                        {
                                            "label": "Username",
                                            "value": "synthetic_photographer",
                                        },
                                    ],
                                    "title": "",
                                }
                            ],
                            "title": "Owner",
                        },
                    ],
                    "fbid": "18000000000000001",
                }
            ],
            {
                "unique_key": "b9ac1b30634f83b8",
                "preview": "Liked post by synthetic_photographer on instagram",
                "asat": datetime(2026, 2, 14, 0, 27, 32, tzinfo=UTC),
                "payload": {
                    "type": "Like",
                    "published": "2026-02-14T00:27:32Z",
                    "object": {
                        "type": "Note",
                        "attributedTo": {
                            "type": "Profile",
                            "name": "synthetic_photographer",
                        },
                        "url": "https://www.instagram.com/stories/synthetic_photographer/3800000000000000001",
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

    def test_record_fields_first(self, extracted_records) -> None:
        record = extracted_records[0]
        assert record.title == "synthetic_photographer"
        assert (
            record.href
            == "https://www.instagram.com/stories/synthetic_photographer/3800000000000000001"
        )
        assert record.timestamp == 1771028852
        assert record.source is not None

    def test_record_fields_second(self, extracted_records) -> None:
        record = extracted_records[1]
        assert record.title == "synthetic_traveler"
        assert (
            record.href
            == "https://www.instagram.com/stories/synthetic_traveler/3800000000000000002"
        )
        assert record.timestamp == 1771115252

    def test_record_fields_third(self, extracted_records) -> None:
        record = extracted_records[2]
        assert record.title == "synthetic_artist"
        assert record.timestamp == 1771201652

    def test_payload_object_has_story_url(self, transformed_rows) -> None:
        for row in transformed_rows:
            obj = row.payload["object"]
            assert "url" in obj
            assert "/stories/" in obj["url"]

    def test_attribution_names(self, transformed_rows) -> None:
        names = [
            row.payload["object"]["attributedTo"]["name"] for row in transformed_rows
        ]
        assert names == [
            "synthetic_photographer",
            "synthetic_traveler",
            "synthetic_artist",
        ]

    def test_preview_includes_liked(self, transformed_rows) -> None:
        for row in transformed_rows:
            assert "Liked" in row.preview
            assert "instagram" in row.preview.lower()
        assert "synthetic_photographer" in transformed_rows[0].preview
        assert "synthetic_traveler" in transformed_rows[1].preview

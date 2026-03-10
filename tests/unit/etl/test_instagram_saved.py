import json
from pathlib import Path

import pytest

from context_use.providers.instagram.saved import (
    InstagramSavedCollectionsPipe,
    InstagramSavedPostsPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import (
    INSTAGRAM_SAVED_COLLECTIONS_JSON,
    INSTAGRAM_SAVED_POSTS_JSON,
)

SAVED_POSTS_ARCHIVE_PATH = "your_instagram_activity/saved/saved_posts.json"
SAVED_COLLECTIONS_ARCHIVE_PATH = "your_instagram_activity/saved/saved_collections.json"


# ---------------------------------------------------------------------------
# Saved posts tests
# ---------------------------------------------------------------------------


class TestInstagramSavedPostsPipe(PipeTestKit):
    pipe_class = InstagramSavedPostsPipe
    expected_extract_count = 1
    expected_transform_count = 1

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{SAVED_POSTS_ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_SAVED_POSTS_JSON).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.title == "synthetic_chef"
        assert record.href == "https://www.instagram.com/p/AAAAAAAAAAA/"
        assert record.timestamp == 1760598407
        assert record.source is not None

    def test_payload_is_add_to_collection(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "AddToCollection"
            assert row.payload["type"] == "Add"

    def test_payload_target_is_favourites(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        target = rows[0].payload["target"]
        assert target["fibreKind"] == "CollectionFavourites"
        assert target["name"] == "Favourites"

    def test_payload_object_is_post(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        obj = rows[0].payload["object"]
        assert obj["type"] == "Note"  # FibrePost extends Note
        assert obj["fibreKind"] == "Post"

    def test_payload_has_attributed_to(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        attr = rows[0].payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "synthetic_chef"

    def test_payload_has_post_url(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        obj = rows[0].payload["object"]
        assert "url" in obj
        assert "AAAAAAAAAAA" in obj["url"]

    def test_preview_includes_saved(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        preview = rows[0].preview
        assert "Saved" in preview
        assert "synthetic_chef" in preview
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
            assert row.interaction_type == "instagram_saved_posts"

    def test_skips_item_without_timestamp(self, tmp_path: Path):
        """Items with no timestamp in 'Saved on' are skipped."""
        data = {
            "saved_saved_media": [
                {
                    "title": "no_timestamp_user",
                    "string_map_data": {
                        "Saved on": {"href": "https://www.instagram.com/p/ZZZ/"}
                    },
                }
            ]
        }
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{SAVED_POSTS_ARCHIVE_PATH}"
        storage.write(key, json.dumps(data).encode())

        pipe = self.pipe_class()
        task = self._make_task(key)
        records = list(pipe.extract(task, storage))
        assert len(records) == 0


# ---------------------------------------------------------------------------
# Saved collections tests
# ---------------------------------------------------------------------------


class TestInstagramSavedCollectionsPipe(PipeTestKit):
    pipe_class = InstagramSavedCollectionsPipe
    # Fixture has 2 collections: "Recipes" (2 items) + "Empty Collection" (0 items)
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{SAVED_COLLECTIONS_ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_SAVED_COLLECTIONS_JSON).encode())
        return storage, key

    def test_record_fields_first_item(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.collection_name == "Recipes"
        assert record.item_author == "synthetic_chef"
        assert record.item_href == "https://www.instagram.com/p/BBBBBBBBBBB/"
        assert record.item_added_at == 1719947100
        assert record.collection_created_at == 1719946907
        assert record.source is not None

    def test_record_fields_second_item(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[1]
        assert record.collection_name == "Recipes"
        assert record.item_author == "pasta_queen"
        assert record.item_href == "https://www.instagram.com/p/CCCCCCCCCCC/"
        assert record.item_added_at == 1719947200

    def test_empty_collection_yields_no_records(self, pipe_fixture):
        """'Empty Collection' header has no child items → no records."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        collection_names = {r.collection_name for r in records}
        assert "Empty Collection" not in collection_names

    def test_payload_is_add_to_collection(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.payload["fibreKind"] == "AddToCollection"
            assert row.payload["type"] == "Add"

    def test_payload_target_is_named_collection(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        target = rows[0].payload["target"]
        assert target["fibreKind"] == "Collection"
        assert target["name"] == "Recipes"
        assert "published" in target  # collection creation time

    def test_payload_object_is_post_with_url(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        obj = rows[0].payload["object"]
        assert obj["type"] == "Note"
        assert obj["fibreKind"] == "Post"
        assert "BBBBBBBBBBB" in obj["url"]

    def test_payload_has_attributed_to(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        attr = rows[0].payload["object"]["attributedTo"]
        assert attr["type"] == "Profile"
        assert attr["name"] == "synthetic_chef"

    def test_preview_includes_saved_to(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        preview = rows[0].preview
        assert "Saved to" in preview
        assert "Recipes" in preview
        assert "instagram" in preview.lower()

    def test_asat_is_item_added_time(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        # First item added_at = 1719947100
        assert rows[0].asat.year >= 2024

    def test_interaction_type(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.interaction_type == "instagram_saved_collections"

    def test_orphan_items_skipped(self, tmp_path: Path):
        """Items before any collection header are skipped."""
        data = {
            "saved_saved_collections": [
                {
                    "string_map_data": {
                        "Name": {
                            "href": "https://www.instagram.com/p/ORPHAN/",
                            "value": "orphan_user",
                        },
                        "Added Time": {"timestamp": 1719947000},
                    }
                },
                {
                    "title": "Collection",
                    "string_map_data": {
                        "Name": {"value": "After Header"},
                        "Creation Time": {"timestamp": 1719946907},
                        "Update Time": {"timestamp": 1719946930},
                    },
                },
                {
                    "string_map_data": {
                        "Name": {
                            "href": "https://www.instagram.com/p/OK/",
                            "value": "valid_user",
                        },
                        "Added Time": {"timestamp": 1719947500},
                    }
                },
            ]
        }
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{SAVED_COLLECTIONS_ARCHIVE_PATH}"
        storage.write(key, json.dumps(data).encode())

        pipe = self.pipe_class()
        task = self._make_task(key)
        records = list(pipe.extract(task, storage))
        assert len(records) == 1
        assert records[0].collection_name == "After Header"
        assert records[0].item_author == "valid_user"

    def test_multiple_collections(self, tmp_path: Path):
        """Items are paired with the correct collection header."""
        data = {
            "saved_saved_collections": [
                {
                    "title": "Collection",
                    "string_map_data": {
                        "Name": {"value": "Alpha"},
                        "Creation Time": {"timestamp": 1000},
                        "Update Time": {"timestamp": 1000},
                    },
                },
                {
                    "string_map_data": {
                        "Name": {
                            "href": "https://www.instagram.com/p/A1/",
                            "value": "user_a",
                        },
                        "Added Time": {"timestamp": 1001},
                    }
                },
                {
                    "title": "Collection",
                    "string_map_data": {
                        "Name": {"value": "Beta"},
                        "Creation Time": {"timestamp": 2000},
                        "Update Time": {"timestamp": 2000},
                    },
                },
                {
                    "string_map_data": {
                        "Name": {
                            "href": "https://www.instagram.com/p/B1/",
                            "value": "user_b",
                        },
                        "Added Time": {"timestamp": 2001},
                    }
                },
            ]
        }
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{SAVED_COLLECTIONS_ARCHIVE_PATH}"
        storage.write(key, json.dumps(data).encode())

        pipe = self.pipe_class()
        task = self._make_task(key)
        records = list(pipe.extract(task, storage))
        assert len(records) == 2
        assert records[0].collection_name == "Alpha"
        assert records[1].collection_name == "Beta"

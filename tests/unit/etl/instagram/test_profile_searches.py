from __future__ import annotations

import json
from pathlib import Path

from context_use.providers.instagram.profile_searches import (
    InstagramProfileSearchesPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.instagram.conftest import INSTAGRAM_PROFILE_SEARCHES_JSON

ARCHIVE_PATH = "logged_information/recent_searches/profile_searches.json"


class TestInstagramProfileSearchesPipe(PipeTestKit):
    pipe_class = InstagramProfileSearchesPipe
    expected_extract_count = 3
    expected_transform_count = 3
    expected_fibre_kind = "Search"
    fixture_data = INSTAGRAM_PROFILE_SEARCHES_JSON
    fixture_key = f"archive/{ARCHIVE_PATH}"

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.username == "synthetic_chef_account"
        assert record.href == "https://www.instagram.com/synthetic_chef_account"
        assert record.timestamp == 1771115155
        assert record.source is not None

    def test_payload_object_is_profile(self, transformed_rows):
        for row in transformed_rows:
            obj = row.payload["object"]
            assert obj["type"] == "Profile"

    def test_profile_has_name_and_url(self, transformed_rows):
        obj = transformed_rows[0].payload["object"]
        assert obj["name"] == "synthetic_chef_account"
        assert "instagram.com/synthetic_chef_account" in obj["url"]

    def test_preview_includes_profile_name(self, transformed_rows):
        preview = transformed_rows[0].preview
        assert "Searched for profile" in preview
        assert "synthetic_chef_account" in preview
        assert "instagram" in preview.lower()

    def test_title_fallback_for_username(self, extracted_records, transformed_rows):
        """When ``value`` is absent, the outer ``title`` is used as username."""
        title_record = extracted_records[2]
        assert title_record.username == "synthetic_fitness_coach"
        assert (
            title_record.href == "https://www.instagram.com/_u/synthetic_fitness_coach"
        )

        obj = transformed_rows[2].payload["object"]
        assert obj["name"] == "synthetic_fitness_coach"

    def test_skips_entries_with_no_username(self, tmp_path: Path):
        """Entries where both ``value`` and ``title`` are empty should be skipped."""
        data = {
            "searches_user": [
                {
                    "title": "",
                    "string_list_data": [
                        {
                            "href": "https://www.instagram.com/has_no_value",
                            "value": "",
                            "timestamp": 1771115155,
                        }
                    ],
                },
                {
                    "title": "",
                    "string_list_data": [
                        {
                            "href": "https://www.instagram.com/valid_user",
                            "value": "valid_user",
                            "timestamp": 1771028852,
                        }
                    ],
                },
            ]
        }
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{ARCHIVE_PATH}"
        storage.write(key, json.dumps(data).encode())
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        assert len(records) == 1
        assert records[0].username == "valid_user"

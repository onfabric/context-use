from __future__ import annotations

import pytest

from context_use.providers.netflix.messages_from_netflix.pipe import (
    NetflixMessagesPipe,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.netflix.conftest import MESSAGES_CSV


class TestNetflixMessagesPipe(PipeTestKit):
    pipe_class = NetflixMessagesPipe
    expected_extract_count = 2
    expected_transform_count = 2
    expected_fibre_kind = "ReceiveMessage"

    @pytest.fixture()
    def pipe_fixture(self, tmp_path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/MESSAGES/MessagesSentByNetflix.csv"
        storage.write(key, MESSAGES_CSV)
        return storage, key

    def test_empty_fields_filtered(self, extracted_records):
        for record in extracted_records:
            assert record.message_name or record.title_name

    def test_actor_is_netflix(self, transformed_rows):
        for row in transformed_rows:
            assert row.payload["actor"]["name"] == "Netflix"

    def test_preview_format(self, transformed_rows):
        for row in transformed_rows:
            assert "Received" in row.preview
            assert "Netflix" in row.preview

    def test_message_name_used_as_content(self, transformed_rows):
        row_with_message = [
            r for r in transformed_rows if "New Episode Alert" in r.preview
        ]
        assert len(row_with_message) == 1

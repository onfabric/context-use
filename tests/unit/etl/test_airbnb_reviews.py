from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.airbnb.reviews import AirbnbReviewsPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import AIRBNB_REVIEWS


class TestAirbnbReviewsPipe(PipeTestKit):
    pipe_class = AirbnbReviewsPipe
    expected_extract_count = 2
    expected_transform_count = 2

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/data/json/reviews.json"
        storage.write(key, json.dumps(AIRBNB_REVIEWS).encode())
        return storage, key

    def test_review_content_includes_rating(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            content = row.payload.get("object", {}).get("content", "")
            assert content.startswith("["), "Content should start with [rating/5]"

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        for r in records:
            assert r.comment
            assert r.rating > 0
            assert r.submitted_at
            assert r.entity_id > 0

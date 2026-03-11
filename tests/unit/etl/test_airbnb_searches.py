from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.airbnb.searches import AirbnbSearchesPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import AIRBNB_SEARCH_HISTORY


class TestAirbnbSearchesPipe(PipeTestKit):
    pipe_class = AirbnbSearchesPipe
    expected_extract_count = 4
    expected_transform_count = 4

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/data/json/search_history.json"
        storage.write(key, json.dumps(AIRBNB_SEARCH_HISTORY).encode())
        return storage, key

    def test_record_locations(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        locations = {r.raw_location for r in records}
        assert "Barcelona" in locations
        assert "London" in locations

    def test_search_preview_contains_location(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert "Searched" in row.preview

    def test_search_without_dates(self, pipe_fixture):
        """The London search has no check-in/check-out dates."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        london = [r for r in records if r.raw_location == "London"][0]
        assert london.checkin_date is None
        assert london.checkout_date is None

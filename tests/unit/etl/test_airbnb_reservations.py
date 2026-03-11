from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.airbnb.reservations import AirbnbReservationsPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import AIRBNB_RESERVATIONS


class TestAirbnbReservationsPipe(PipeTestKit):
    pipe_class = AirbnbReservationsPipe
    expected_extract_count = 3
    expected_transform_count = 3

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/data/json/reservations.json"
        storage.write(key, json.dumps(AIRBNB_RESERVATIONS).encode())
        return storage, key

    def test_skips_booking_sessions(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        assert len(records) == 3, "Should only extract reservations, not sessions"

    def test_all_statuses_included(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        statuses = {r.status for r in records}
        assert "accepted" in statuses
        assert "cancelled" in statuses

    def test_payload_has_listing_url(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            obj = row.payload.get("object", {})
            assert obj.get("url", "").startswith("https://www.airbnb.com/rooms/")

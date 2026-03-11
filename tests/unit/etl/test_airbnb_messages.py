from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.airbnb.messages import AirbnbMessagesPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import AIRBNB_MESSAGES


class TestAirbnbMessagesPipe(PipeTestKit):
    pipe_class = AirbnbMessagesPipe
    expected_extract_count = 6
    expected_transform_count = 6

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/data/json/messages.json"
        storage.write(key, json.dumps(AIRBNB_MESSAGES).encode())
        return storage, key

    def test_skips_service_messages(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        for r in records:
            assert r.account_type != "service"

    def test_skips_non_text_messages(self, pipe_fixture):
        """The fixture's MessageContent system message should be filtered."""
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        for r in records:
            assert r.text.strip()

    def test_send_and_receive(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        kinds = [r.payload["fibreKind"] for r in rows]
        assert "SendMessage" in kinds
        assert "ReceiveMessage" in kinds

    def test_thread_collection_id(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        collections = set()
        for row in rows:
            obj = row.payload.get("object", {})
            ctx = obj.get("context", {})
            if ctx and ctx.get("id"):
                collections.add(ctx["id"])
        assert len(collections) == 2, "Should have 2 distinct thread collections"

from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.chatgpt.conversations import ChatGPTConversationsPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import CHATGPT_CONVERSATIONS


class TestChatGPTConversationsPipe(PipeTestKit):
    pipe_class = ChatGPTConversationsPipe
    expected_extract_count = 5
    expected_transform_count = 5

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/conversations.json"
        storage.write(key, json.dumps(CHATGPT_CONVERSATIONS).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.role in ("user", "assistant")
        assert record.content
        assert record.conversation_id is not None
        assert record.conversation_title is not None

    def test_skips_system_messages(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        all_roles = [r.role for r in records]
        assert "system" not in all_roles

    def test_send_and_receive(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        kinds = [r.payload["fibreKind"] for r in rows]
        assert "SendMessage" in kinds
        assert "ReceiveMessage" in kinds

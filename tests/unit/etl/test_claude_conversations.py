
import json
from pathlib import Path

import pytest

from context_use.providers.claude.conversations import ClaudeConversationsPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.conftest import CLAUDE_CONVERSATIONS


class TestClaudeConversationsPipe(PipeTestKit):
    pipe_class = ClaudeConversationsPipe
    # 4 messages in the first conversation; 1 empty message in the second is skipped
    expected_extract_count = 4
    expected_transform_count = 4

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/conversations.json"
        storage.write(key, json.dumps(CLAUDE_CONVERSATIONS).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.role in ("human", "assistant")
        assert record.content
        assert record.conversation_id is not None
        assert record.conversation_title is not None

    def test_skips_empty_text_messages(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        for r in records:
            assert r.content.strip(), "Empty-text messages must be filtered out"

    def test_send_and_receive(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        kinds = [r.payload["fibreKind"] for r in rows]
        assert "SendMessage" in kinds
        assert "ReceiveMessage" in kinds

    def test_tool_call_noise_stripped(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        for r in records:
            assert "not supported on your current device" not in r.content
            assert "tool_use" not in r.content
            assert "tool_result" not in r.content

    def test_collection_url(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            obj = row.payload.get("object", {})
            ctx = obj.get("context", {})
            if ctx:
                assert ctx.get("id", "").startswith("https://claude.ai/chat/")

from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.etl.core.types import ThreadRow
from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.etl.providers.chatgpt.conversations import ChatGPTConversationsPipe
from context_use.etl.providers.chatgpt.schemas import ChatGPTConversationRecord
from context_use.storage.disk import DiskStorage
from tests.conftest import CHATGPT_CONVERSATIONS


@pytest.fixture()
def chatgpt_storage(tmp_path: Path):
    storage = DiskStorage(str(tmp_path / "store"))
    key = "archive/conversations.json"
    storage.write(key, json.dumps(CHATGPT_CONVERSATIONS).encode())
    return storage, key


def _make_task(key: str) -> EtlTask:
    return EtlTask(
        archive_id="a1",
        provider="chatgpt",
        interaction_type="chatgpt_conversations",
        source_uri=key,
        status=EtlTaskStatus.CREATED.value,
    )


class TestChatGPTConversationsPipeExtract:
    """Tests for the extract phase (individual record yielding)."""

    def test_yields_records(self, chatgpt_storage):
        storage, key = chatgpt_storage
        pipe = ChatGPTConversationsPipe()
        task = _make_task(key)

        records = list(pipe.extract(task, storage))
        assert len(records) >= 1
        assert all(isinstance(r, ChatGPTConversationRecord) for r in records)

    def test_record_fields(self, chatgpt_storage):
        storage, key = chatgpt_storage
        pipe = ChatGPTConversationsPipe()
        task = _make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.role in ("user", "assistant")
        assert record.content
        assert record.conversation_id is not None
        assert record.conversation_title is not None

    def test_skips_system_messages(self, chatgpt_storage):
        storage, key = chatgpt_storage
        pipe = ChatGPTConversationsPipe()
        task = _make_task(key)

        records = list(pipe.extract(task, storage))
        all_roles = [r.role for r in records]
        assert "system" not in all_roles

    def test_row_count(self, chatgpt_storage):
        """
        2 conversations: conv-001 has user + assistant (system skipped) = 2,
        conv-002 has user + assistant + user = 3. Total = 5.
        """
        storage, key = chatgpt_storage
        pipe = ChatGPTConversationsPipe()
        task = _make_task(key)

        records = list(pipe.extract(task, storage))
        assert len(records) == 5

    def test_record_schema_declared(self):
        assert ChatGPTConversationsPipe.record_schema is ChatGPTConversationRecord


class TestChatGPTConversationsPipeTransform:
    """Tests for the transform phase (record → ThreadRow)."""

    def test_produces_thread_rows(self, chatgpt_storage):
        storage, key = chatgpt_storage
        pipe = ChatGPTConversationsPipe()
        task = _make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) >= 1
        assert all(isinstance(r, ThreadRow) for r in rows)

    def test_thread_row_fields(self, chatgpt_storage):
        storage, key = chatgpt_storage
        pipe = ChatGPTConversationsPipe()
        task = _make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.unique_key.startswith("chatgpt_conversations:")
            assert row.provider == "chatgpt"
            assert row.interaction_type == "chatgpt_conversations"
            assert row.version
            assert row.asat is not None

    def test_payload_is_dict(self, chatgpt_storage):
        storage, key = chatgpt_storage
        pipe = ChatGPTConversationsPipe()
        task = _make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert isinstance(row.payload, dict)
            assert "fibre_kind" in row.payload

    def test_send_and_receive(self, chatgpt_storage):
        storage, key = chatgpt_storage
        pipe = ChatGPTConversationsPipe()
        task = _make_task(key)

        rows = list(pipe.run(task, storage))
        kinds = [r.payload["fibre_kind"] for r in rows]
        assert "SendMessage" in kinds
        assert "ReceiveMessage" in kinds

    def test_previews_non_empty(self, chatgpt_storage):
        storage, key = chatgpt_storage
        pipe = ChatGPTConversationsPipe()
        task = _make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.preview, "Preview should not be empty"

    def test_class_vars(self):
        assert ChatGPTConversationsPipe.provider == "chatgpt"
        assert ChatGPTConversationsPipe.interaction_type == "chatgpt_conversations"
        assert ChatGPTConversationsPipe.archive_version == "v1"
        assert ChatGPTConversationsPipe.archive_path == "conversations.json"

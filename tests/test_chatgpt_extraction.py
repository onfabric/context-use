"""Tests for ChatGPT extraction strategy."""

import json
from pathlib import Path

import pytest

from context_use.etl.core.types import ExtractedBatch
from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.etl.providers.chatgpt.conversations import (
    ChatGPTConversationsExtractionStrategy,
)
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


class TestChatGPTExtraction:
    def test_returns_extracted_batches(self, chatgpt_storage):
        storage, key = chatgpt_storage
        strategy = ChatGPTConversationsExtractionStrategy()
        task = _make_task(key)

        batches = strategy.extract(task, storage)
        assert len(batches) >= 1
        assert isinstance(batches[0], ExtractedBatch)

    def test_records_are_typed(self, chatgpt_storage):
        storage, key = chatgpt_storage
        strategy = ChatGPTConversationsExtractionStrategy()
        task = _make_task(key)

        batches = strategy.extract(task, storage)
        for record in batches[0].records:
            assert isinstance(record, ChatGPTConversationRecord)

    def test_record_fields(self, chatgpt_storage):
        storage, key = chatgpt_storage
        strategy = ChatGPTConversationsExtractionStrategy()
        task = _make_task(key)

        batches = strategy.extract(task, storage)
        record = batches[0].records[0]
        assert record.role in ("user", "assistant")
        assert record.content
        assert record.conversation_id is not None
        assert record.conversation_title is not None

    def test_skips_system_messages(self, chatgpt_storage):
        storage, key = chatgpt_storage
        strategy = ChatGPTConversationsExtractionStrategy()
        task = _make_task(key)

        batches = strategy.extract(task, storage)
        all_roles = [r.role for batch in batches for r in batch.records]
        # system messages should be filtered out
        assert "system" not in all_roles

    def test_row_count(self, chatgpt_storage):
        """
        2 conversations: 2 user + 2 assistant = 5 msgs total,
        but 1 is system -> 4 rows.
        """
        storage, key = chatgpt_storage
        strategy = ChatGPTConversationsExtractionStrategy()
        task = _make_task(key)

        batches = strategy.extract(task, storage)
        total = sum(len(b) for b in batches)
        # conv-001: user + assistant (system skipped) = 2
        # conv-002: user + assistant + user = 3
        assert total == 5

    def test_record_schema_declared(self):
        assert (
            ChatGPTConversationsExtractionStrategy.record_schema
            is ChatGPTConversationRecord
        )

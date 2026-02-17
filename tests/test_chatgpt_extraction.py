"""Tests for ChatGPT extraction strategy."""

import json
from pathlib import Path

import pytest

from contextuse.core.types import TaskMetadata
from contextuse.providers.chatgpt.conversations import (
    ChatGPTConversationsExtractionStrategy,
)
from contextuse.storage.disk import DiskStorage
from tests.conftest import CHATGPT_CONVERSATIONS


@pytest.fixture()
def chatgpt_storage(tmp_path: Path):
    storage = DiskStorage(str(tmp_path / "store"))
    key = "archive/conversations.json"
    storage.write(key, json.dumps(CHATGPT_CONVERSATIONS).encode())
    return storage, key


class TestChatGPTExtraction:
    def test_extracts_correct_columns(self, chatgpt_storage):
        storage, key = chatgpt_storage
        strategy = ChatGPTConversationsExtractionStrategy()
        task = TaskMetadata(
            archive_id="a1",
            etl_task_id="t1",
            provider="chatgpt",
            interaction_type="chatgpt_conversations",
            filenames=[key],
        )

        batches = strategy.extract(task, storage)
        assert len(batches) >= 1

        df = batches[0]
        expected_cols = {"role", "content", "create_time", "conversation_id", "conversation_title", "source"}
        assert expected_cols.issubset(set(df.columns))

    def test_skips_system_messages(self, chatgpt_storage):
        storage, key = chatgpt_storage
        strategy = ChatGPTConversationsExtractionStrategy()
        task = TaskMetadata(
            archive_id="a1",
            etl_task_id="t1",
            provider="chatgpt",
            interaction_type="chatgpt_conversations",
            filenames=[key],
        )

        batches = strategy.extract(task, storage)
        all_rows = batches[0]
        # system messages should be filtered out
        assert "system" not in all_rows["role"].values

    def test_row_count(self, chatgpt_storage):
        """2 conversations: 2 user + 2 assistant = 5 msgs total, but 1 is system → 4 rows."""
        storage, key = chatgpt_storage
        strategy = ChatGPTConversationsExtractionStrategy()
        task = TaskMetadata(
            archive_id="a1",
            etl_task_id="t1",
            provider="chatgpt",
            interaction_type="chatgpt_conversations",
            filenames=[key],
        )

        batches = strategy.extract(task, storage)
        total = sum(len(b) for b in batches)
        # conv-001: user + assistant (system skipped) = 2
        # conv-002: user + assistant + user = 3
        assert total == 5


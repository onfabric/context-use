from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from context_use.models.etl_task import EtlTask, EtlTaskStatus
from context_use.providers.chatgpt.conversations import ChatGPTConversationsPipe
from context_use.providers.chatgpt.schemas import (
    ChatGPTConversation,
    ChatGPTMappingNode,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.chatgpt.conftest import CHATGPT_CONVERSATIONS


class TestChatGPTConversationsPipe(PipeTestKit):
    pipe_class = ChatGPTConversationsPipe
    expected_extract_count = 5
    expected_transform_count = 5
    fixture_data = CHATGPT_CONVERSATIONS
    fixture_key = "archive/conversations.json"

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.role in ("user", "assistant")
        assert record.content
        assert record.conversation_id is not None
        assert record.conversation_title is not None

    def test_skips_system_messages(self, extracted_records):
        all_roles = [r.role for r in extracted_records]
        assert "system" not in all_roles

    def test_send_and_receive(self, transformed_rows):
        kinds = [r.payload["fibreKind"] for r in transformed_rows]
        assert "SendMessage" in kinds
        assert "ReceiveMessage" in kinds


class TestChatGPTConversationSchema:
    def test_valid_conversation(self) -> None:
        raw = {
            "title": "Test",
            "conversation_id": "conv-1",
            "mapping": {
                "msg-1": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["hello"]},
                        "create_time": 1700000000.0,
                    }
                }
            },
        }
        conv = ChatGPTConversation.model_validate(raw)
        assert conv.title == "Test"
        assert conv.conversation_id == "conv-1"
        assert len(conv.mapping) == 1
        assert conv.mapping["msg-1"].message is not None

    def test_missing_mapping_raises(self) -> None:
        raw = {"title": "Test", "conversation_id": "conv-1"}
        with pytest.raises(ValidationError):
            ChatGPTConversation.model_validate(raw)

    def test_optional_fields(self) -> None:
        raw = {"mapping": {"node-1": {}}}
        conv = ChatGPTConversation.model_validate(raw)
        assert conv.title is None
        assert conv.conversation_id is None
        assert conv.mapping["node-1"].message is None

    def test_extra_fields_tolerated(self) -> None:
        raw = {
            "title": "Test",
            "conversation_id": "conv-1",
            "mapping": {},
            "create_time": 1700000000.0,
            "unknown_field": "ignored",
        }
        conv = ChatGPTConversation.model_validate(raw)
        assert conv.title == "Test"

    def test_node_with_null_message(self) -> None:
        node = ChatGPTMappingNode.model_validate({"message": None})
        assert node.message is None

    def test_node_with_extra_fields(self) -> None:
        node = ChatGPTMappingNode.model_validate(
            {"message": None, "id": "node-1", "children": ["node-2"]}
        )
        assert node.message is None


class TestChatGPTFileSchemaGate:
    def test_malformed_file_skipped(self, tmp_path) -> None:
        malformed = [{"title": "Bad", "conversation_id": "conv-bad"}]
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/conversations.json"
        storage.write(key, json.dumps(malformed).encode())

        pipe = ChatGPTConversationsPipe()
        task = EtlTask(
            archive_id="a1",
            provider="chatgpt",
            interaction_type="chatgpt_conversations",
            source_uris=[key],
            status=EtlTaskStatus.CREATED.value,
        )
        rows = list(pipe.run(task, storage))
        assert rows == []
        assert pipe.error_count == 1

    def test_valid_file_processes_normally(self, tmp_path) -> None:
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/conversations.json"
        storage.write(key, json.dumps(CHATGPT_CONVERSATIONS).encode())

        pipe = ChatGPTConversationsPipe()
        task = EtlTask(
            archive_id="a1",
            provider="chatgpt",
            interaction_type="chatgpt_conversations",
            source_uris=[key],
            status=EtlTaskStatus.CREATED.value,
        )
        rows = list(pipe.run(task, storage))
        assert len(rows) == 5
        assert pipe.error_count == 0

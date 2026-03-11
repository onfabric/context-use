from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from context_use.etl.core.types import ThreadRow
from context_use.models.etl_task import EtlTask, EtlTaskStatus
from context_use.providers.claude.conversations import ClaudeConversationsPipe
from context_use.providers.claude.schemas import (
    ClaudeChatMessage,
    ClaudeContentBlock,
    ClaudeConversation,
    ClaudeConversationRecord,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.claude.conftest import CLAUDE_CONVERSATIONS


class TestClaudeConversationsPipe(PipeTestKit):
    pipe_class = ClaudeConversationsPipe
    expected_extract_count = 4
    expected_transform_count = 4
    fixture_data = CLAUDE_CONVERSATIONS
    fixture_key = "archive/conversations.json"

    def test_record_fields(
        self, extracted_records: list[ClaudeConversationRecord]
    ) -> None:
        record = extracted_records[0]
        assert record.role in ("human", "assistant")
        assert record.content
        assert record.conversation_id is not None
        assert record.conversation_title is not None

    def test_skips_empty_text_messages(
        self, extracted_records: list[ClaudeConversationRecord]
    ) -> None:
        for r in extracted_records:
            assert r.content.strip(), "Empty-text messages must be filtered out"

    def test_send_and_receive(self, transformed_rows: list[ThreadRow]) -> None:
        kinds = [r.payload["fibreKind"] for r in transformed_rows]
        assert "SendMessage" in kinds
        assert "ReceiveMessage" in kinds

    def test_tool_call_noise_stripped(
        self, extracted_records: list[ClaudeConversationRecord]
    ) -> None:
        for r in extracted_records:
            assert "not supported on your current device" not in r.content
            assert "tool_use" not in r.content
            assert "tool_result" not in r.content

    def test_collection_url(self, transformed_rows: list[ThreadRow]) -> None:
        for row in transformed_rows:
            obj = row.payload.get("object", {})
            ctx = obj.get("context", {})
            if ctx:
                assert ctx.get("id", "").startswith("https://claude.ai/chat/")

    def test_source_captures_raw_message(
        self, extracted_records: list[ClaudeConversationRecord]
    ) -> None:
        for r in extracted_records:
            assert r.source is not None
            raw = json.loads(r.source)
            assert "sender" in raw


class TestClaudeConversationFileSchema:
    def test_valid_conversation(self) -> None:
        data = {
            "uuid": "conv-1",
            "name": "Test",
            "chat_messages": [
                {
                    "sender": "human",
                    "content": [{"type": "text", "text": "hello"}],
                    "created_at": "2025-01-01T00:00:00Z",
                }
            ],
        }
        conv = ClaudeConversation.model_validate(data)
        assert conv.uuid == "conv-1"
        assert conv.name == "Test"
        assert len(conv.chat_messages) == 1
        assert conv.chat_messages[0].sender == "human"

    def test_extra_fields_tolerated(self) -> None:
        data = {
            "uuid": "conv-1",
            "name": "Test",
            "summary": "some summary",
            "account": {"uuid": "acct-1"},
            "some_future_field": 42,
            "chat_messages": [
                {
                    "sender": "human",
                    "content": [{"type": "text", "text": "hi", "citations": []}],
                    "created_at": "2025-01-01T00:00:00Z",
                    "uuid": "msg-1",
                    "attachments": [],
                    "files": [],
                    "unknown_field": True,
                }
            ],
        }
        conv = ClaudeConversation.model_validate(data)
        assert len(conv.chat_messages) == 1

    def test_missing_chat_messages_raises(self) -> None:
        with pytest.raises(ValidationError):
            ClaudeConversation.model_validate({"uuid": "conv-1", "name": "Test"})

    def test_missing_sender_raises(self) -> None:
        with pytest.raises(ValidationError):
            ClaudeChatMessage.model_validate(
                {"content": [{"type": "text", "text": "hi"}]}
            )

    def test_missing_content_block_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            ClaudeContentBlock.model_validate({"text": "hi"})

    def test_empty_chat_messages_valid(self) -> None:
        conv = ClaudeConversation.model_validate(
            {"chat_messages": [], "uuid": "conv-1"}
        )
        assert conv.chat_messages == []

    def test_content_defaults_to_empty_list(self) -> None:
        msg = ClaudeChatMessage.model_validate({"sender": "human"})
        assert msg.content == []

    def test_invalid_conversation_skipped_in_extraction(self, tmp_path: str) -> None:
        fixture = [
            {"not_a_conversation": True},
            {
                "uuid": "conv-valid",
                "name": "Valid",
                "chat_messages": [
                    {
                        "sender": "human",
                        "content": [{"type": "text", "text": "hello"}],
                        "created_at": "2025-01-01T00:00:00Z",
                    }
                ],
            },
        ]
        storage = DiskStorage(str(tmp_path))
        key = "archive/conversations.json"
        storage.write(key, json.dumps(fixture).encode())

        pipe = ClaudeConversationsPipe()
        task = EtlTask(
            archive_id="a1",
            provider="claude",
            interaction_type="claude_conversations",
            source_uris=[key],
            status=EtlTaskStatus.CREATED.value,
        )
        records = list(pipe.extract(task, storage))
        assert len(records) == 1
        assert records[0].conversation_id == "conv-valid"

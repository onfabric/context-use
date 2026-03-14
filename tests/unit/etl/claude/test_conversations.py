from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from context_use.etl.core.types import ThreadRow
from context_use.models.etl_task import EtlTask, EtlTaskStatus
from context_use.providers.claude.conversations.pipe import (
    ClaudeConversationsPipe,
    ClaudeRole,
)
from context_use.providers.claude.conversations.record import ClaudeConversationRecord
from context_use.providers.claude.conversations.pipe import ClaudeRole
from context_use.providers.claude.conversations.schemas import (
    ChatMessage,
    ContentItem,
    Model,
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


_VALID_CONTENT_ITEM: dict = {
    "start_timestamp": "2025-01-01T00:00:00Z",
    "stop_timestamp": "2025-01-01T00:00:01Z",
    "flags": None,
    "type": "text",
    "text": "hello",
}

_VALID_MESSAGE: dict = {
    "uuid": "msg-1",
    "text": "hello",
    "content": [_VALID_CONTENT_ITEM],
    "sender": "human",
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z",
    "attachments": [],
    "files": [],
}

_VALID_CONVERSATION: dict = {
    "uuid": "conv-1",
    "name": "Test",
    "summary": "",
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z",
    "account": {"uuid": "acct-1"},
    "chat_messages": [_VALID_MESSAGE],
}


class TestClaudeConversationFileSchema:
    def test_valid_conversation(self) -> None:
        conv = Model.model_validate(_VALID_CONVERSATION)
        assert conv.uuid == "conv-1"
        assert conv.name == "Test"
        assert len(conv.chat_messages) == 1
        assert conv.chat_messages[0].sender == "human"

    def test_extra_fields_tolerated(self) -> None:
        data = {
            **_VALID_CONVERSATION,
            "some_future_field": 42,
            "chat_messages": [
                {**_VALID_MESSAGE, "unknown_field": True},
            ],
        }
        conv = Model.model_validate(data)
        assert len(conv.chat_messages) == 1

    def test_missing_required_conversation_field_raises(self) -> None:
        data = {k: v for k, v in _VALID_CONVERSATION.items() if k != "uuid"}
        with pytest.raises(ValidationError):
            Model.model_validate(data)

    def test_missing_required_message_field_raises(self) -> None:
        data = {k: v for k, v in _VALID_MESSAGE.items() if k != "sender"}
        with pytest.raises(ValidationError):
            ChatMessage.model_validate(data)

    def test_missing_content_item_type_raises(self) -> None:
        data = {k: v for k, v in _VALID_CONTENT_ITEM.items() if k != "type"}
        with pytest.raises(ValidationError):
            ContentItem.model_validate(data)

    def test_content_item_text_is_optional(self) -> None:
        item = ContentItem.model_validate(
            {
                "start_timestamp": None,
                "stop_timestamp": None,
                "flags": None,
                "type": "tool_use",
            }
        )
        assert item.text is None

    def test_flags_accepts_any_value(self) -> None:
        for flags_val in [None, "x", 0, True, {}]:
            item = ContentItem.model_validate(
                {**_VALID_CONTENT_ITEM, "flags": flags_val}
            )
            assert item.flags == flags_val

    def test_claude_role_values(self) -> None:
        assert ClaudeRole.HUMAN == "human"
        assert ClaudeRole.ASSISTANT == "assistant"

    def test_invalid_conversation_fails_file(self, tmp_path: str) -> None:
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
        rows = list(pipe.run(task, storage))
        assert rows == []
        assert pipe.error_count == 1

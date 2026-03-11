from __future__ import annotations

from context_use.providers.claude.conversations import ClaudeConversationsPipe
from context_use.testing import PipeTestKit
from tests.unit.etl.claude.conftest import CLAUDE_CONVERSATIONS


class TestClaudeConversationsPipe(PipeTestKit):
    pipe_class = ClaudeConversationsPipe
    expected_extract_count = 4
    expected_transform_count = 4
    fixture_data = CLAUDE_CONVERSATIONS
    fixture_key = "archive/conversations.json"

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.role in ("human", "assistant")
        assert record.content
        assert record.conversation_id is not None
        assert record.conversation_title is not None

    def test_skips_empty_text_messages(self, extracted_records):
        for r in extracted_records:
            assert r.content.strip(), "Empty-text messages must be filtered out"

    def test_send_and_receive(self, transformed_rows):
        kinds = [r.payload["fibreKind"] for r in transformed_rows]
        assert "SendMessage" in kinds
        assert "ReceiveMessage" in kinds

    def test_tool_call_noise_stripped(self, extracted_records):
        for r in extracted_records:
            assert "not supported on your current device" not in r.content
            assert "tool_use" not in r.content
            assert "tool_result" not in r.content

    def test_collection_url(self, transformed_rows):
        for row in transformed_rows:
            obj = row.payload.get("object", {})
            ctx = obj.get("context", {})
            if ctx:
                assert ctx.get("id", "").startswith("https://claude.ai/chat/")

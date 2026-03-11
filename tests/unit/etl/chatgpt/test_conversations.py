from __future__ import annotations

from context_use.providers.chatgpt.conversations import ChatGPTConversationsPipe
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

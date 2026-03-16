from __future__ import annotations

from datetime import UTC, datetime

from context_use.proxy.threads import (
    INTERACTION_TYPE,
    PROVIDER,
    messages_to_thread_rows,
)


class TestMessagesToThreadRows:
    def test_user_message_becomes_send(self) -> None:
        messages = [{"role": "user", "content": "Hello"}]
        rows = messages_to_thread_rows(messages)

        assert len(rows) == 1
        row = rows[0]
        assert row.provider == PROVIDER
        assert row.interaction_type == INTERACTION_TYPE
        assert row.payload["fibreKind"] == "SendMessage"
        assert row.payload["object"]["content"] == "Hello"

    def test_assistant_message_becomes_receive(self) -> None:
        messages = [{"role": "assistant", "content": "Hi there!"}]
        rows = messages_to_thread_rows(messages)

        assert len(rows) == 1
        assert rows[0].payload["fibreKind"] == "ReceiveMessage"
        assert rows[0].payload["object"]["content"] == "Hi there!"

    def test_system_and_tool_messages_are_skipped(self) -> None:
        messages = [
            {"role": "system", "content": "Be helpful"},
            {"role": "tool", "content": "result"},
            {"role": "function", "content": "output"},
            {"role": "user", "content": "Hi"},
        ]
        rows = messages_to_thread_rows(messages)

        assert len(rows) == 1
        assert rows[0].payload["object"]["content"] == "Hi"

    def test_multimodal_extracts_text_only(self) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What's in this image?"},
                    {"type": "image_url", "image_url": {"url": "https://..."}},
                ],
            }
        ]
        rows = messages_to_thread_rows(messages)

        assert len(rows) == 1
        assert rows[0].payload["object"]["content"] == "What's in this image?"

    def test_empty_content_is_skipped(self) -> None:
        messages = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": ""},
        ]
        rows = messages_to_thread_rows(messages)

        assert len(rows) == 0

    def test_session_id_sets_collection(self) -> None:
        messages = [{"role": "user", "content": "Hello"}]
        rows = messages_to_thread_rows(messages, session_id="session-123")

        assert len(rows) == 1
        context = rows[0].payload["object"].get("context")
        assert context is not None
        assert context["id"] == "https://unknown/session/session-123"

    def test_no_session_id_omits_collection(self) -> None:
        messages = [{"role": "user", "content": "Hello"}]
        rows = messages_to_thread_rows(messages)

        assert rows[0].payload["object"].get("context") is None

    def test_full_conversation(self) -> None:
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "Thanks!"},
        ]
        rows = messages_to_thread_rows(messages)

        assert len(rows) == 3
        assert rows[0].payload["fibreKind"] == "SendMessage"
        assert rows[1].payload["fibreKind"] == "ReceiveMessage"
        assert rows[2].payload["fibreKind"] == "SendMessage"

    def test_custom_timestamp(self) -> None:
        ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        messages = [{"role": "user", "content": "Hello"}]
        rows = messages_to_thread_rows(messages, now=ts)

        assert rows[0].asat == ts

    def test_unique_keys_differ_for_different_content(self) -> None:
        rows_a = messages_to_thread_rows([{"role": "user", "content": "Hello"}])
        rows_b = messages_to_thread_rows([{"role": "user", "content": "Goodbye"}])

        assert rows_a[0].unique_key != rows_b[0].unique_key

    def test_preview_is_set(self) -> None:
        messages = [{"role": "user", "content": "Hello world"}]
        rows = messages_to_thread_rows(messages)

        assert rows[0].preview
        assert "Hello world" in rows[0].preview

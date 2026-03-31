from __future__ import annotations

import json

import pytest

from context_use.models.etl_task import EtlTask, EtlTaskStatus
from context_use.providers.telegram.conversations.pipe import (
    TelegramConversationsPipe,
    _flatten_text,
)
from context_use.providers.telegram.conversations.schemas import Model, Text
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.telegram.conftest import TELEGRAM_RESULT


class TestTelegramConversationsPipe(PipeTestKit):
    pipe_class = TelegramConversationsPipe
    expected_extract_count = 6
    expected_transform_count = 6
    fixture_data = TELEGRAM_RESULT
    fixture_key = "archive/result.json"

    def test_service_messages_skipped(self, extracted_records) -> None:
        for r in extracted_records:
            assert r.text != ""

    def test_empty_text_skipped(self, extracted_records) -> None:
        message_ids_extracted = {
            json.loads(r.source)["id"] for r in extracted_records if r.source
        }
        assert 1005 not in message_ids_extracted

    def test_self_detection(self, extracted_records) -> None:
        self_records = [r for r in extracted_records if r.is_self]
        non_self_records = [r for r in extracted_records if not r.is_self]
        assert len(self_records) == 3
        assert len(non_self_records) == 3
        for r in self_records:
            assert r.from_id == "user12345678"

    def test_send_and_receive(self, transformed_rows) -> None:
        kinds = [r.payload["fibreKind"] for r in transformed_rows]
        assert "SendMessage" in kinds
        assert "ReceiveMessage" in kinds
        assert kinds.count("SendMessage") == 3
        assert kinds.count("ReceiveMessage") == 3

    def test_collection_ids_per_chat(self, transformed_rows) -> None:
        collection_ids = {r.collection_id for r in transformed_rows}
        assert len(collection_ids) == 2

    def test_rich_text_flattened(self, extracted_records) -> None:
        rich = [r for r in extracted_records if "cool-article" in r.text]
        assert len(rich) == 1
        assert rich[0].text == (
            "Look at this link: https://example.com/cool-article pretty interesting!"
        )

    def test_chat_metadata_on_records(self, extracted_records) -> None:
        chat_types = {r.chat_type for r in extracted_records}
        assert chat_types == {"personal_chat"}
        chat_names = {r.chat_name for r in extracted_records}
        assert "Bob Johnson" in chat_names
        assert "Carol Davis" in chat_names


class TestFlattenText:
    def test_plain_string(self) -> None:
        assert _flatten_text("hello") == "hello"

    def test_list_of_strings(self) -> None:
        assert _flatten_text(["hello", " ", "world"]) == "hello world"

    def test_list_with_rich_parts(self) -> None:
        parts: list[str | Text] = [
            "See ",
            Text(type="link", text="https://example.com"),
            " here",
        ]
        assert _flatten_text(parts) == "See https://example.com here"

    def test_empty_string(self) -> None:
        assert _flatten_text("") == ""

    def test_empty_list(self) -> None:
        assert _flatten_text([]) == ""


class TestTelegramSchema:
    def test_valid_chat(self) -> None:
        raw = {
            "type": "personal_chat",
            "id": 1,
            "messages": [
                {
                    "id": 1,
                    "type": "message",
                    "date": "2025-01-01T00:00:00",
                    "date_unixtime": "1735689600",
                    "from": "Alice",
                    "from_id": "user1",
                    "text": "hello",
                    "text_entities": [{"type": "plain", "text": "hello"}],
                }
            ],
            "name": "Bob",
        }
        chat = Model.model_validate(raw)
        assert chat.type == "personal_chat"
        assert len(chat.messages) == 1
        assert chat.messages[0].from_ == "Alice"

    def test_chat_without_name(self) -> None:
        raw = {
            "type": "saved_messages",
            "id": 1,
            "messages": [],
        }
        chat = Model.model_validate(raw)
        assert chat.name is None

    def test_message_with_list_text(self) -> None:
        raw = {
            "type": "personal_chat",
            "id": 1,
            "messages": [
                {
                    "id": 1,
                    "type": "message",
                    "date": "2025-01-01T00:00:00",
                    "date_unixtime": "1735689600",
                    "text": ["hello ", {"type": "bold", "text": "world"}],
                    "text_entities": [],
                }
            ],
        }
        chat = Model.model_validate(raw)
        msg = chat.messages[0]
        assert isinstance(msg.text, list)


class TestTelegramFileEdgeCases:
    def _make_task(self, key: str) -> EtlTask:
        return EtlTask(
            archive_id="a1",
            provider="telegram",
            interaction_type="telegram_conversations",
            source_uris=[key],
            status=EtlTaskStatus.CREATED.value,
        )

    def test_no_personal_information(self, tmp_path) -> None:
        data = {
            "chats": {
                "list": [
                    {
                        "type": "personal_chat",
                        "id": 1,
                        "name": "Bob",
                        "messages": [
                            {
                                "id": 1,
                                "type": "message",
                                "date": "2025-01-01T00:00:00",
                                "date_unixtime": "1735689600",
                                "from": "Alice",
                                "from_id": "user1",
                                "text": "hello",
                                "text_entities": [{"type": "plain", "text": "hello"}],
                            }
                        ],
                    }
                ]
            }
        }
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/result.json"
        storage.write(key, json.dumps(data).encode())

        pipe = TelegramConversationsPipe()
        rows = list(pipe.run(self._make_task(key), storage))
        assert len(rows) == 1
        assert rows[0].payload["fibreKind"] == "ReceiveMessage"

    @pytest.mark.parametrize(
        "text",
        ["", " ", "   "],
    )
    def test_whitespace_only_text_skipped(self, tmp_path, text: str) -> None:
        data = {
            "chats": {
                "list": [
                    {
                        "type": "personal_chat",
                        "id": 1,
                        "name": "Bob",
                        "messages": [
                            {
                                "id": 1,
                                "type": "message",
                                "date": "2025-01-01T00:00:00",
                                "date_unixtime": "1735689600",
                                "from": "Alice",
                                "from_id": "user1",
                                "text": text,
                                "text_entities": [],
                            }
                        ],
                    }
                ]
            }
        }
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/result.json"
        storage.write(key, json.dumps(data).encode())

        pipe = TelegramConversationsPipe()
        task = self._make_task(key)
        records = list(pipe.extract(task, storage))
        assert records == []

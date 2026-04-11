from __future__ import annotations

from datetime import UTC, datetime

from context_use.models.thread import Thread


def _make_send_message_payload() -> dict:
    return {
        "type": "Create",
        "fibre_kind": "SendMessage",
        "object": {
            "type": "Note",
            "fibre_kind": "TextMessage",
            "content": "hello world",
        },
        "target": {"type": "Application", "name": "assistant"},
    }


def _make_create_object_payload(*, caption: str | None = None) -> dict:
    obj: dict = {"type": "Image", "url": "http://example.com/pic.jpg"}
    if caption is not None:
        obj["content"] = caption
    return {
        "type": "Create",
        "fibre_kind": "Create",
        "object": obj,
    }


class TestThreadPreviewProperty:
    def test_preview_computed_from_payload(self) -> None:
        thread = Thread(
            unique_key="k1",
            provider="Instagram",
            interaction_type="instagram_posts",
            payload=_make_create_object_payload(),
            version="1.1.0",
            asat=datetime(2025, 1, 1, tzinfo=UTC),
        )
        assert thread.preview == "Posted image on Instagram"

    def test_preview_send_message(self) -> None:
        thread = Thread(
            unique_key="k2",
            provider="ChatGPT",
            interaction_type="chatgpt_conversations",
            payload=_make_send_message_payload(),
            version="1.1.0",
            asat=datetime(2025, 1, 1, tzinfo=UTC),
        )
        assert "Sent" in thread.preview
        assert "assistant" in thread.preview


class TestThreadGetContent:
    def test_returns_stored_content_when_set(self) -> None:
        thread = Thread(
            unique_key="k1",
            provider="Instagram",
            interaction_type="instagram_posts",
            payload=_make_create_object_payload(),
            version="1.1.0",
            asat=datetime(2025, 1, 1, tzinfo=UTC),
            content="latte art at Blue Bottle Coffee",
        )
        assert thread.get_content() == "latte art at Blue Bottle Coffee"

    def test_falls_back_to_payload_when_content_is_none(self) -> None:
        thread = Thread(
            unique_key="k2",
            provider="ChatGPT",
            interaction_type="chatgpt_conversations",
            payload=_make_send_message_payload(),
            version="1.1.0",
            asat=datetime(2025, 1, 1, tzinfo=UTC),
        )
        assert thread.get_content() == "hello world"

    def test_falls_back_to_empty_when_payload_has_no_content(self) -> None:
        thread = Thread(
            unique_key="k3",
            provider="Instagram",
            interaction_type="instagram_posts",
            payload=_make_create_object_payload(),
            version="1.1.0",
            asat=datetime(2025, 1, 1, tzinfo=UTC),
        )
        assert thread.get_content() == ""

    def test_caption_extracted_from_payload(self) -> None:
        thread = Thread(
            unique_key="k4",
            provider="Instagram",
            interaction_type="instagram_posts",
            payload=_make_create_object_payload(caption="sunset at the beach"),
            version="1.1.0",
            asat=datetime(2025, 1, 1, tzinfo=UTC),
        )
        assert thread.get_content() == "sunset at the beach"

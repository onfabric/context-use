"""Unit tests for ActivityStreams payload models and make_thread_payload."""

import datetime

from context_use.etl.payload.core import make_thread_payload
from context_use.etl.payload.models import (
    Application,
    FibreCreateObject,
    FibreReceiveMessage,
    FibreSendMessage,
    FibreTextMessage,
    Image,
    Video,
)


class TestFibreModels:
    def test_text_message_preview(self):
        msg = FibreTextMessage(content="Hello World")
        assert msg.get_preview() == 'message "Hello World"'

    def test_text_message_truncation(self):
        long = "x" * 200
        msg = FibreTextMessage(content=long)
        preview = msg.get_preview()
        assert "..." in preview
        assert len(preview) < 120

    def test_send_message_roundtrip(self):
        msg = FibreTextMessage(content="hi")
        target = Application(name="assistant")
        send = FibreSendMessage(object=msg, target=target)

        d = send.to_dict()
        assert d["fibre_kind"] == "SendMessage"
        assert d["object"]["content"] == "hi"
        assert d["target"]["name"] == "assistant"

        # Unique key should be deterministic
        assert send.unique_key_suffix() == send.unique_key_suffix()

    def test_receive_message_preview(self):
        msg = FibreTextMessage(content="world")
        actor = Application(name="bot")
        recv = FibreReceiveMessage(object=msg, actor=actor)

        preview = recv.get_preview("TestProvider")
        assert "Received" in preview
        assert "bot" in preview

    def test_create_object_image(self):
        img = Image(url="http://example.com/pic.jpg")
        create = FibreCreateObject(object=img)
        assert create.get_preview("Instagram") == "Posted image on Instagram"

    def test_create_object_video(self):
        vid = Video(url="http://example.com/clip.mp4")
        create = FibreCreateObject(object=vid)
        assert create.get_preview() == "Posted video"


class TestMakeThreadPayload:
    def test_send_message(self):
        data = {
            "type": "Create",
            "fibre_kind": "SendMessage",
            "object": {
                "type": "Note",
                "fibre_kind": "TextMessage",
                "content": "hi",
            },
            "target": {"type": "Application", "name": "bot"},
        }
        payload = make_thread_payload(data)
        assert isinstance(payload, FibreSendMessage)

    def test_create_object(self):
        data = {
            "type": "Create",
            "fibre_kind": "Create",
            "object": {"type": "Video", "url": "http://example.com/v.mp4"},
        }
        payload = make_thread_payload(data)
        assert isinstance(payload, FibreCreateObject)


class TestFibreAsat:
    def test_get_asat_with_published(self):
        dt = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)
        msg = FibreTextMessage(content="test", published=dt)
        assert msg.get_asat() == dt

    def test_get_asat_without_published(self):
        msg = FibreTextMessage(content="test")
        assert msg.get_asat() is None

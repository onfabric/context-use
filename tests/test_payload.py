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
        msg = FibreTextMessage(content="Hello World")  # pyright: ignore[reportCallIssue]
        assert msg.get_preview() == 'message "Hello World"'

    def test_text_message_truncation(self):
        long = "x" * 200
        msg = FibreTextMessage(content=long)  # pyright: ignore[reportCallIssue]
        preview = msg.get_preview()
        assert preview is not None
        assert "..." in preview
        assert len(preview) < 120

    def test_send_message_roundtrip(self):
        msg = FibreTextMessage(content="hi")  # pyright: ignore[reportCallIssue]
        target = Application(name="assistant")  # pyright: ignore[reportCallIssue]
        send = FibreSendMessage(object=msg, target=target)  # pyright: ignore[reportCallIssue]

        d = send.to_dict()
        assert d["fibre_kind"] == "SendMessage"
        assert d["object"]["content"] == "hi"
        assert d["target"]["name"] == "assistant"

        # Unique key should be deterministic
        assert send.unique_key_suffix() == send.unique_key_suffix()

    def test_receive_message_preview(self):
        msg = FibreTextMessage(content="world")  # pyright: ignore[reportCallIssue]
        actor = Application(name="bot")  # pyright: ignore[reportCallIssue]
        recv = FibreReceiveMessage(object=msg, actor=actor)  # pyright: ignore[reportCallIssue]

        preview = recv.get_preview("TestProvider")
        assert preview is not None
        assert "Received" in preview
        assert "bot" in preview

    def test_create_object_image(self):
        img = Image(url="http://example.com/pic.jpg")  # pyright: ignore[reportCallIssue]
        create = FibreCreateObject(object=img)  # pyright: ignore[reportCallIssue]
        assert create.get_preview("Instagram") == "Posted image on Instagram"

    def test_create_object_video(self):
        vid = Video(url="http://example.com/clip.mp4")  # pyright: ignore[reportCallIssue]
        create = FibreCreateObject(object=vid)  # pyright: ignore[reportCallIssue]
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
        msg = FibreTextMessage(content="test", published=dt)  # pyright: ignore[reportCallIssue]
        assert msg.get_asat() == dt

    def test_get_asat_without_published(self):
        msg = FibreTextMessage(content="test")  # pyright: ignore[reportCallIssue]
        assert msg.get_asat() is None

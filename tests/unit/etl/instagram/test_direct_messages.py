from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.providers.instagram.direct_messages import InstagramDirectMessagesPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.instagram.conftest import INSTAGRAM_DM_INBOX_JSON

INBOX_ARCHIVE_PATH = (
    "your_instagram_activity/messages/inbox/bobsmith_1234567890/message_1.json"
)


class TestInstagramDirectMessagesPipe(PipeTestKit):
    pipe_class = InstagramDirectMessagesPipe
    # 5 messages in the fixture; all have at least content or a share link
    expected_extract_count = 5
    expected_transform_count = 5

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = f"archive/{INBOX_ARCHIVE_PATH}"
        storage.write(key, json.dumps(INSTAGRAM_DM_INBOX_JSON).encode())
        return storage, key

    def test_record_fields(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        record = records[0]
        assert record.sender_name
        assert record.content is not None
        assert record.timestamp_ms > 0
        assert record.thread_path == "inbox/bobsmith_1234567890"
        assert record.title == "bobsmith"
        assert record.source is not None

    def test_sender_identification(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        sent_messages = [r for r in records if not r.is_inbound]
        received_messages = [r for r in records if r.is_inbound]

        assert len(sent_messages) == 2
        assert len(received_messages) == 3
        for r in sent_messages:
            assert r.sender_name == "alice_synthetic"
        for r in received_messages:
            assert r.sender_name == "bobsmith"

    def test_send_and_receive_payloads(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        kinds = [r.payload["fibreKind"] for r in rows]
        assert "SendMessage" in kinds
        assert "ReceiveMessage" in kinds

    def test_send_message_target_is_other_person(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        sent = [r for r in rows if r.payload["fibreKind"] == "SendMessage"]
        assert len(sent) == 2
        for row in sent:
            assert row.payload["target"]["name"] == "bobsmith"

    def test_receive_message_actor_is_sender(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        received = [r for r in rows if r.payload["fibreKind"] == "ReceiveMessage"]
        assert len(received) == 3
        for row in received:
            assert row.payload["actor"]["name"] == "bobsmith"

    def test_conversation_context_collection(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            obj = row.payload["object"]
            assert obj["type"] == "Note"
            ctx = obj["context"]
            assert ctx["type"] == "Collection"
            assert (
                ctx["id"]
                == "https://www.instagram.com/direct/inbox/bobsmith_1234567890"
            )
            assert ctx["name"] == "bobsmith"

    def test_story_reply_content_and_url(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        story_rows = [
            r for r in rows if "Replied to story" in r.payload["object"]["content"]
        ]
        assert len(story_rows) == 1
        row = story_rows[0]
        assert "Sounds great" in row.payload["object"]["content"]
        assert "stories" in row.payload["object"]["url"]

    def test_story_reply_share_fields_in_record(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        story_records = [r for r in records if r.link and "/stories/" in r.link]
        assert len(story_records) == 2
        reply_with_text = next(r for r in story_records if r.content is not None)
        assert reply_with_text.content == "Sounds great, see you there!"
        assert reply_with_text.share_text is None
        assert reply_with_text.original_content_owner is None

    def test_story_share_without_content(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        no_text_story_rows = [
            r
            for r in rows
            if r.payload["object"].get("content") == "Replied to a story"
        ]
        assert len(no_text_story_rows) == 1
        assert "stories" in no_text_story_rows[0].payload["object"]["url"]

    def test_shared_reel_with_caption_in_fixture(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        shared_rows = [
            r
            for r in rows
            if "Shared from @coffeecreator" in r.payload["object"].get("content", "")
        ]
        assert len(shared_rows) == 1
        obj = shared_rows[0].payload["object"]
        assert "great reel about coffee" in obj["content"]
        assert obj["url"] == "https://www.instagram.com/reel/ABC123/"

    def test_asat_from_timestamp_ms(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.asat.year == 2024

    def test_interaction_type(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        for row in rows:
            assert row.interaction_type == "instagram_direct_messages"

    def test_skips_messages_without_content_or_share(self, tmp_path: Path):
        data = {
            "participants": [{"name": "charlie"}, {"name": "alice"}],
            "messages": [
                {
                    "sender_name": "alice",
                    "timestamp_ms": 1725000000000,
                    "is_geoblocked_for_viewer": False,
                    "is_unsent_image_by_messenger_kid_parent": False,
                },
                {
                    "sender_name": "charlie",
                    "timestamp_ms": 1725000001000,
                    "content": "Hello!",
                    "is_geoblocked_for_viewer": False,
                    "is_unsent_image_by_messenger_kid_parent": False,
                },
            ],
            "title": "charlie",
            "is_still_participant": True,
            "thread_path": "inbox/charlie_111",
            "magic_words": [],
        }
        storage = DiskStorage(str(tmp_path / "store"))
        key = (
            "archive/your_instagram_activity/messages/inbox/charlie_111/message_1.json"
        )
        storage.write(key, json.dumps(data).encode())
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        assert len(records) == 1
        assert records[0].content == "Hello!"

    def test_attachment_placeholder_ignored_in_payload(self, tmp_path: Path):
        data = {
            "participants": [{"name": "dave"}, {"name": "alice"}],
            "messages": [
                {
                    "sender_name": "dave",
                    "timestamp_ms": 1725000000000,
                    "content": "dave sent an attachment.",
                    "share": {
                        "link": "https://www.instagram.com/reel/XYZ/",
                        "share_text": "Cool reel caption",
                        "original_content_owner": "creator123",
                    },
                    "is_geoblocked_for_viewer": False,
                    "is_unsent_image_by_messenger_kid_parent": False,
                },
            ],
            "title": "dave",
            "is_still_participant": True,
            "thread_path": "inbox/dave_333",
            "magic_words": [],
        }
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/your_instagram_activity/messages/inbox/dave_333/message_1.json"
        storage.write(key, json.dumps(data).encode())
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        assert len(records) == 1
        assert records[0].content == "dave sent an attachment."

        rows = list(pipe.run(task, storage))
        obj = rows[0].payload["object"]
        assert "Shared from @creator123" in obj["content"]
        assert "dave sent an attachment." not in obj["content"]

    def test_shared_post_with_caption(self, tmp_path: Path):
        data = {
            "participants": [{"name": "eve"}, {"name": "alice"}],
            "messages": [
                {
                    "sender_name": "eve",
                    "timestamp_ms": 1725000000000,
                    "content": "eve sent an attachment.",
                    "share": {
                        "link": "https://www.instagram.com/reel/ABC123/",
                        "share_text": "This is a great reel about startups",
                        "original_content_owner": "techcreator",
                    },
                    "is_geoblocked_for_viewer": False,
                    "is_unsent_image_by_messenger_kid_parent": False,
                },
            ],
            "title": "eve",
            "is_still_participant": True,
            "thread_path": "inbox/eve_444",
            "magic_words": [],
        }
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/your_instagram_activity/messages/inbox/eve_444/message_1.json"
        storage.write(key, json.dumps(data).encode())
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        assert len(records) == 1
        record = records[0]
        assert record.content == "eve sent an attachment."
        assert record.share_text == "This is a great reel about startups"
        assert record.original_content_owner == "techcreator"
        assert record.link == "https://www.instagram.com/reel/ABC123/"

        rows = list(pipe.run(task, storage))
        obj = rows[0].payload["object"]
        assert "Shared from @techcreator" in obj["content"]
        assert "great reel about startups" in obj["content"]
        assert obj["url"] == "https://www.instagram.com/reel/ABC123/"

    def test_share_only_message_extracted(self, tmp_path: Path):
        data = {
            "participants": [{"name": "frank"}, {"name": "alice"}],
            "messages": [
                {
                    "sender_name": "alice",
                    "timestamp_ms": 1725000000000,
                    "share": {"link": "https://www.instagram.com/p/abc123/"},
                    "is_geoblocked_for_viewer": False,
                    "is_unsent_image_by_messenger_kid_parent": False,
                },
            ],
            "title": "frank",
            "is_still_participant": True,
            "thread_path": "inbox/frank_555",
            "magic_words": [],
        }
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/your_instagram_activity/messages/inbox/frank_555/message_1.json"
        storage.write(key, json.dumps(data).encode())
        pipe = self.pipe_class()
        task = self._make_task(key)

        records = list(pipe.extract(task, storage))
        assert len(records) == 1
        assert records[0].content is None
        assert records[0].link == "https://www.instagram.com/p/abc123/"
        assert records[0].is_inbound is False

        rows = list(pipe.run(task, storage))
        obj = rows[0].payload["object"]
        assert obj["url"] == "https://www.instagram.com/p/abc123/"

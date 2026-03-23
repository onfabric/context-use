from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from context_use.providers.instagram.direct_messages.pipe import (
    InstagramDirectMessagesPipe,
)
from context_use.providers.instagram.direct_messages.schemas import (
    InstagramDirectMessageManifest,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.instagram.conftest import INSTAGRAM_DM_INBOX_JSON


class TestInstagramDirectMessagesPipe(PipeTestKit):
    pipe_class = InstagramDirectMessagesPipe
    expected_extract_count = 5
    expected_transform_count = 5
    fixture_data = INSTAGRAM_DM_INBOX_JSON
    fixture_key = (
        "archive/your_instagram_activity/messages/inbox/"
        "bobsmith_1234567890/message_1.json"
    )
    snapshot_cases = [
        (
            {
                "participants": [
                    {"name": "synthetic_friend"},
                    {"name": "alice_synthetic"},
                ],
                "messages": [
                    {
                        "sender_name": "alice_synthetic",
                        "timestamp_ms": 1725022880969,
                        "content": (
                            "Hey synthetic friend, are we still on for coffee tomorrow?"
                        ),
                        "is_geoblocked_for_viewer": False,
                        "is_unsent_image_by_messenger_kid_parent": False,
                    }
                ],
                "title": "synthetic_friend",
                "is_still_participant": True,
                "thread_path": "inbox/synthetic_friend_1234567890",
                "magic_words": [],
            },
            {
                "preview": (
                    'Sent message "Hey synthetic friend, are we still on for '
                    'coffee tomorrow?" to synthetic_friend on Instagram'
                ),
                "asat": datetime(2024, 8, 30, 13, 1, 20, 969000, tzinfo=UTC),
                "payload": {
                    "fibreKind": "SendMessage",
                    "type": "Create",
                    "published": "2024-08-30T13:01:20.969000Z",
                    "target": {"name": "synthetic_friend", "type": "Profile"},
                    "object": {
                        "content": (
                            "Hey synthetic friend, are we still on for coffee tomorrow?"
                        ),
                        "context": {
                            "id": "https://www.instagram.com/direct/inbox/synthetic_friend_1234567890",
                            "name": "synthetic_friend",
                            "type": "Collection",
                        },
                        "fibreKind": "TextMessage",
                        "type": "Note",
                    },
                },
            },
        ),
        (
            {
                "participants": [
                    {"name": "synthetic_friend"},
                    {"name": "alice_synthetic"},
                ],
                "messages": [
                    {
                        "sender_name": "synthetic_friend",
                        "timestamp_ms": 1724700000000,
                        "share": {
                            "link": "https://www.instagram.com/stories/synthetic_story_author/9876543210987654321"
                        },
                        "is_geoblocked_for_viewer": False,
                        "is_unsent_image_by_messenger_kid_parent": False,
                    }
                ],
                "title": "synthetic_friend",
                "is_still_participant": True,
                "thread_path": "inbox/synthetic_friend_1234567890",
                "magic_words": [],
            },
            {
                "preview": (
                    'Received message "Replied to a story" from '
                    "synthetic_friend on Instagram"
                ),
                "asat": datetime(2024, 8, 26, 19, 20, tzinfo=UTC),
                "payload": {
                    "actor": {"name": "synthetic_friend", "type": "Profile"},
                    "fibreKind": "ReceiveMessage",
                    "type": "Create",
                    "published": "2024-08-26T19:20:00Z",
                    "object": {
                        "content": "Replied to a story",
                        "context": {
                            "id": "https://www.instagram.com/direct/inbox/synthetic_friend_1234567890",
                            "name": "synthetic_friend",
                            "type": "Collection",
                        },
                        "fibreKind": "TextMessage",
                        "type": "Note",
                        "url": "https://www.instagram.com/stories/synthetic_story_author/9876543210987654321",
                    },
                },
            },
        ),
    ]

    def test_file_schema_gates_missing_thread_path(self, tmp_path: Path):
        data = {
            "participants": [{"name": "ghost"}, {"name": "alice"}],
            "messages": [
                {
                    "sender_name": "ghost",
                    "timestamp_ms": 1725000000000,
                    "content": "Hello!",
                },
            ],
            "title": "ghost",
        }
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/your_instagram_activity/messages/inbox/ghost_999/message_1.json"
        storage.write(key, json.dumps(data).encode())
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 0
        assert pipe.error_count == 1

    def test_file_schema_gates_missing_messages(self, tmp_path: Path):
        data = {
            "title": "ghost",
            "thread_path": "inbox/ghost_999",
        }
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/your_instagram_activity/messages/inbox/ghost_999/message_1.json"
        storage.write(key, json.dumps(data).encode())
        pipe = self.pipe_class()
        task = self._make_task(key)

        rows = list(pipe.run(task, storage))
        assert len(rows) == 0
        assert pipe.error_count == 1

    def test_file_schema_tolerates_extra_fields(self):
        data = {
            "participants": [{"name": "bob"}],
            "messages": [
                {
                    "sender_name": "bob",
                    "timestamp_ms": 1725000000000,
                    "content": "Hi",
                    "is_geoblocked_for_viewer": False,
                    "some_new_field": "value",
                },
            ],
            "title": "bob",
            "thread_path": "inbox/bob_123",
            "is_still_participant": True,
            "magic_words": [],
            "future_field": "tolerated",
        }
        manifest = InstagramDirectMessageManifest.model_validate(data)
        assert manifest.thread_path == "inbox/bob_123"
        assert len(manifest.messages) == 1
        assert manifest.messages[0].sender_name == "bob"

    def test_record_fields(self, extracted_records):
        record = extracted_records[0]
        assert record.sender_name
        assert record.content is not None
        assert record.timestamp_ms > 0
        assert record.thread_path == "inbox/bobsmith_1234567890"
        assert record.title == "bobsmith"
        assert record.source is not None

    def test_sender_identification(self, extracted_records):
        sent_messages = [r for r in extracted_records if r.sender_name != r.title]
        received_messages = [r for r in extracted_records if r.sender_name == r.title]

        assert len(sent_messages) == 2
        assert len(received_messages) == 3
        for r in sent_messages:
            assert r.sender_name == "alice_synthetic"
        for r in received_messages:
            assert r.sender_name == "bobsmith"

    def test_send_and_receive_payloads(self, transformed_rows):
        kinds = [r.payload["fibreKind"] for r in transformed_rows]
        assert "SendMessage" in kinds
        assert "ReceiveMessage" in kinds

    def test_send_message_target_is_other_person(self, transformed_rows):
        sent = [r for r in transformed_rows if r.payload["fibreKind"] == "SendMessage"]
        assert len(sent) == 2
        for row in sent:
            assert row.payload["target"]["name"] == "bobsmith"

    def test_receive_message_actor_is_sender(self, transformed_rows):
        received = [
            r for r in transformed_rows if r.payload["fibreKind"] == "ReceiveMessage"
        ]
        assert len(received) == 3
        for row in received:
            assert row.payload["actor"]["name"] == "bobsmith"

    def test_conversation_context_collection(self, transformed_rows):
        for row in transformed_rows:
            obj = row.payload["object"]
            assert obj["type"] == "Note"
            ctx = obj["context"]
            assert ctx["type"] == "Collection"
            assert (
                ctx["id"]
                == "https://www.instagram.com/direct/inbox/bobsmith_1234567890"
            )
            assert ctx["name"] == "bobsmith"

    def test_story_reply_content_and_url(self, transformed_rows):
        story_rows = [
            r
            for r in transformed_rows
            if "Replied to story" in r.payload["object"]["content"]
        ]
        assert len(story_rows) == 1
        row = story_rows[0]
        assert "Sounds great" in row.payload["object"]["content"]
        assert "stories" in row.payload["object"]["url"]

    def test_story_reply_share_fields_in_record(self, extracted_records):
        story_records = [
            r for r in extracted_records if r.link and "/stories/" in r.link
        ]
        assert len(story_records) == 2
        reply_with_text = next(r for r in story_records if r.content is not None)
        assert reply_with_text.content == "Sounds great, see you there!"
        assert reply_with_text.share_text is None
        assert reply_with_text.original_content_owner is None

    def test_story_share_without_content(self, transformed_rows):
        no_text_story_rows = [
            r
            for r in transformed_rows
            if r.payload["object"].get("content") == "Replied to a story"
        ]
        assert len(no_text_story_rows) == 1
        assert "stories" in no_text_story_rows[0].payload["object"]["url"]

    def test_shared_reel_with_caption_in_fixture(self, transformed_rows):
        shared_rows = [
            r
            for r in transformed_rows
            if "Shared from @coffeecreator" in r.payload["object"].get("content", "")
        ]
        assert len(shared_rows) == 1
        obj = shared_rows[0].payload["object"]
        assert "great reel about coffee" in obj["content"]
        assert obj["url"] == "https://www.instagram.com/reel/ABC123/"

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
        assert records[0].sender_name != records[0].title

        rows = list(pipe.run(task, storage))
        obj = rows[0].payload["object"]
        assert obj["url"] == "https://www.instagram.com/p/abc123/"

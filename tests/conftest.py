"""Shared test fixtures: mini JSON data, zip builder, pre-configured ctx."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Generator
from pathlib import Path

import pytest

from context_use import ContextUse
from context_use.db.postgres import PostgresBackend
from context_use.etl.models.base import Base
from context_use.storage.disk import DiskStorage

# ---------------------------------------------------------------------------
# Mini ChatGPT conversations fixture
# ---------------------------------------------------------------------------

CHATGPT_CONVERSATIONS = [
    {
        "title": "Hello World",
        "conversation_id": "conv-001",
        "mapping": {
            "msg-1": {
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["Hi there!"]},
                    "create_time": 1700000000.0,
                }
            },
            "msg-2": {
                "message": {
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "text",
                        "parts": ["Hello! How can I help you?"],
                    },
                    "create_time": 1700000001.0,
                }
            },
            "msg-3": {
                "message": {
                    "author": {"role": "system"},
                    "content": {
                        "content_type": "text",
                        "parts": ["You are a helpful assistant."],
                    },
                    "create_time": 1700000002.0,
                }
            },
        },
    },
    {
        "title": "Python Help",
        "conversation_id": "conv-002",
        "mapping": {
            "msg-4": {
                "message": {
                    "author": {"role": "user"},
                    "content": {
                        "content_type": "text",
                        "parts": ["How do I read a file in Python?"],
                    },
                    "create_time": 1700001000.0,
                }
            },
            "msg-5": {
                "message": {
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "text",
                        "parts": [
                            "You can use open() to read a file. \
                            For example: with open('file.txt') as f: data = f.read()"
                        ],
                    },
                    "create_time": 1700001001.0,
                }
            },
            "msg-6": {
                "message": {
                    "author": {"role": "user"},
                    "content": {
                        "content_type": "text",
                        "parts": ["Thanks!"],
                    },
                    "create_time": 1700001002.0,
                }
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Mini Instagram fixtures
# ---------------------------------------------------------------------------

INSTAGRAM_STORIES_JSON = {
    "ig_stories": [
        {
            "uri": "media/stories/202512/story1.mp4",
            "creation_timestamp": 1765390423,
            "title": "",
            "media_metadata": {
                "video_metadata": {"exif_data": [{}]},
            },
        },
        {
            "uri": "media/stories/202512/story2.jpg",
            "creation_timestamp": 1765390500,
            "title": "My Day",
        },
    ]
}

INSTAGRAM_REELS_JSON = {
    "ig_reels_media": [
        {
            "media": [
                {
                    "uri": "media/reels/202506/reel1.mp4",
                    "creation_timestamp": 1750896174,
                    "title": "Fun Reel",
                }
            ]
        }
    ]
}


# ---------------------------------------------------------------------------
# Zip builder helper
# ---------------------------------------------------------------------------


def build_zip(files: dict[str, bytes | str]) -> bytes:
    """Create an in-memory zip archive from a dict of {path: content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode("utf-8")
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture()
def chatgpt_zip(tmp_path: Path) -> Path:
    """Write a ChatGPT zip to a temp file and return the path."""
    data = build_zip({"conversations.json": json.dumps(CHATGPT_CONVERSATIONS)})
    p = tmp_path / "chatgpt-export.zip"
    p.write_bytes(data)
    return p


@pytest.fixture()
def instagram_zip(tmp_path: Path) -> Path:
    """Write an Instagram zip to a temp file and return the path."""
    data = build_zip(
        {
            "your_instagram_activity/media/stories.json": json.dumps(
                INSTAGRAM_STORIES_JSON
            ),
            "your_instagram_activity/media/reels.json": json.dumps(
                INSTAGRAM_REELS_JSON
            ),
            # Add a dummy media file to mimic real archive
            "media/stories/202512/story1.mp4": b"\x00" * 10,
            "media/stories/202512/story2.jpg": b"\xff\xd8\xff" + b"\x00" * 7,
            "media/reels/202506/reel1.mp4": b"\x00" * 10,
        }
    )
    p = tmp_path / "instagram-export.zip"
    p.write_bytes(data)
    return p


@pytest.fixture(scope="session")
def db() -> PostgresBackend:
    """Used in each test to get a fresh database."""
    backend = PostgresBackend(
        host="localhost",
        port=5432,
        database="context_use_tests",
        user="postgres",
        password="postgres",
    )
    backend.init_db()
    return backend


@pytest.fixture(autouse=True)
def _clean_tables(db: PostgresBackend) -> Generator[None]:
    """Used after each test to clean the database."""
    yield
    with db.session_scope() as session:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())


@pytest.fixture()
def ctx(tmp_path: Path, db: PostgresBackend) -> ContextUse:
    storage = DiskStorage(base_path=str(tmp_path / "storage"))
    return ContextUse(storage=storage, db=db)

from __future__ import annotations

import io
import zipfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from context_use.batch.grouper import CollectionGrouper, ThreadGroup
from context_use.memories.prompt.base import GroupContext
from context_use.models import Archive, EtlTask
from context_use.models.etl_task import EtlTaskStatus
from context_use.providers.claude.conversations.pipe import ClaudeConversationsPipe
from context_use.storage.disk import DiskStorage
from context_use.store.sqlite import SqliteStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"

_MEMORIES_FIXTURE = (
    FIXTURES_DIR
    / "users"
    / "alice"
    / "claude"
    / "v1"
    / "memories"
    / "conversations.json"
)

ALICE_CHATGPT_DIR = FIXTURES_DIR / "users" / "alice" / "chatgpt" / "v1" / "threads"
ALICE_GOOGLE_DIR = FIXTURES_DIR / "users" / "alice" / "google" / "v1" / "threads"
ALICE_INSTAGRAM_DIR = FIXTURES_DIR / "users" / "alice" / "instagram" / "v1" / "threads"


def build_zip(files: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode("utf-8")
            zf.writestr(name, data)
    return buf.getvalue()


def zip_fixture_dir(fixture_dir: Path, dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(fixture_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(fixture_dir))
    return dest


@pytest.fixture()
def chatgpt_zip(tmp_path: Path) -> Path:
    return zip_fixture_dir(ALICE_CHATGPT_DIR, tmp_path / "chatgpt-export.zip")


@pytest.fixture()
def google_zip(tmp_path: Path) -> Path:
    return zip_fixture_dir(ALICE_GOOGLE_DIR, tmp_path / "google-export.zip")


@pytest.fixture()
def instagram_zip(tmp_path: Path) -> Path:
    return zip_fixture_dir(ALICE_INSTAGRAM_DIR, tmp_path / "instagram-export.zip")


@pytest.fixture(scope="session")
async def thread_store(
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncGenerator[SqliteStore]:
    storage = DiskStorage(str(tmp_path_factory.mktemp("storage")))
    key = "archive/conversations.json"
    storage.write(key, _MEMORIES_FIXTURE.read_bytes())

    pipe = ClaudeConversationsPipe()
    task = EtlTask(
        archive_id="memories-fixture",
        provider="claude",
        interaction_type="claude_conversations",
        source_uris=[key],
        status=EtlTaskStatus.CREATED.value,
    )
    thread_rows = list(pipe.run(task, storage))

    store = SqliteStore(path=str(tmp_path_factory.mktemp("store") / "threads.db"))
    await store.init(embedding_dimensions=4)

    archive = Archive(id="memories-fixture", provider="claude")
    await store.create_archive(archive)
    await store.create_task(task)
    await store.insert_threads(thread_rows, task.id)

    yield store
    await store.close()


@pytest.fixture(scope="session")
async def conversation_groups(thread_store: SqliteStore) -> list[ThreadGroup]:
    threads = await thread_store.get_unprocessed_threads(
        interaction_types=["claude_conversations"]
    )
    return CollectionGrouper().group(threads)


@pytest.fixture(scope="session")
def group_contexts(conversation_groups: list[ThreadGroup]) -> list[GroupContext]:
    return [
        GroupContext(group_id=g.group_id, new_threads=g.threads)
        for g in conversation_groups
    ]

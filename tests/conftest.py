from __future__ import annotations

import io
import json
import os
import zipfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from context_use import ContextUse
from context_use.db.postgres import PostgresBackend
from context_use.etl.models.base import Base
from context_use.storage.disk import DiskStorage

FIXTURES_DIR = Path(__file__).parent / "fixtures"

ALICE_CHATGPT_DIR = FIXTURES_DIR / "users" / "alice" / "chatgpt" / "v1"
ALICE_INSTAGRAM_DIR = FIXTURES_DIR / "users" / "alice" / "instagram" / "v1"


CHATGPT_CONVERSATIONS: list[dict] = json.loads(
    (ALICE_CHATGPT_DIR / "conversations.json").read_text()
)


INSTAGRAM_STORIES_JSON: dict = json.loads(
    (
        ALICE_INSTAGRAM_DIR / "your_instagram_activity" / "media" / "stories.json"
    ).read_text()
)

INSTAGRAM_REELS_JSON: dict = json.loads(
    (
        ALICE_INSTAGRAM_DIR / "your_instagram_activity" / "media" / "reels.json"
    ).read_text()
)


def build_zip(files: dict[str, bytes | str]) -> bytes:
    """Create an in-memory zip archive from a dict of {path: content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode("utf-8")
            zf.writestr(name, data)
    return buf.getvalue()


def zip_fixture_dir(fixture_dir: Path, dest: Path) -> Path:
    """Zip an entire fixture directory tree into *dest*."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(fixture_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(fixture_dir))
    return dest


@pytest.fixture()
def chatgpt_zip(tmp_path: Path) -> Path:
    """Zip alice's synthetic ChatGPT archive into a temp file."""
    return zip_fixture_dir(ALICE_CHATGPT_DIR, tmp_path / "chatgpt-export.zip")


@pytest.fixture()
def instagram_zip(tmp_path: Path) -> Path:
    """Zip alice's synthetic Instagram archive into a temp file."""
    return zip_fixture_dir(ALICE_INSTAGRAM_DIR, tmp_path / "instagram-export.zip")


class Settings:
    def __init__(self) -> None:
        self.host = str(os.getenv("POSTGRES_HOST"))
        self.port = int(str(os.getenv("POSTGRES_PORT")))
        self.database = str(os.getenv("POSTGRES_DB"))
        self.user = str(os.getenv("POSTGRES_USER"))
        self.password = str(os.getenv("POSTGRES_PASSWORD"))


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture()
async def db(settings: Settings) -> AsyncGenerator[PostgresBackend]:
    backend = PostgresBackend(
        host=settings.host,
        port=settings.port,
        database=settings.database,
        user=settings.user,
        password=settings.password,
    )
    await backend.init_db()
    yield backend
    await backend.get_engine().dispose()


@pytest.fixture(autouse=True)
async def _clean_tables(db: PostgresBackend) -> AsyncGenerator[None]:
    """Used after each test to clean the database."""
    yield
    async with db.session_scope() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())


@pytest.fixture()
def ctx(tmp_path: Path, db: PostgresBackend) -> ContextUse:
    storage = DiskStorage(base_path=str(tmp_path / "storage"))
    return ContextUse(storage=storage, db=db)

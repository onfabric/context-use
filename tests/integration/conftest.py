from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from context_use import ContextUse
from context_use.db.models import Base
from context_use.db.postgres import PostgresBackend
from context_use.storage.disk import DiskStorage
from context_use.store.postgres import PostgresStore


def pytest_collection_modifyitems(items: list, config) -> None:  # noqa: ANN001
    """Auto-mark every test in the integration directory."""
    marker = pytest.mark.integration
    for item in items:
        item.add_marker(marker)


class Settings:
    def __init__(self) -> None:
        self.host = os.getenv("POSTGRES_HOST", "localhost")
        self.port = int(os.getenv("POSTGRES_PORT", "5432"))
        self.database = os.getenv("POSTGRES_DB", "context_use_test")
        self.user = os.getenv("POSTGRES_USER", "postgres")
        self.password = os.getenv("POSTGRES_PASSWORD", "postgres")


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture()
async def db(settings: Settings) -> AsyncGenerator[PostgresBackend]:
    """Create a DB backend with table cleanup before and after each test."""
    backend = PostgresBackend(
        host=settings.host,
        port=settings.port,
        database=settings.database,
        user=settings.user,
        password=settings.password,
    )
    await backend.init_db()

    async with backend.session_scope() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())

    yield backend

    async with backend.session_scope() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())

    await backend.get_engine().dispose()


@pytest.fixture()
async def store(settings: Settings) -> AsyncGenerator[PostgresStore]:
    """Create a PostgresStore with a clean slate for each test."""
    pg_store = PostgresStore.from_params(
        host=settings.host,
        port=settings.port,
        database=settings.database,
        user=settings.user,
        password=settings.password,
    )
    await pg_store.init()
    await pg_store.reset()

    yield pg_store

    await pg_store.reset()
    await pg_store.close()


@pytest.fixture()
def ctx(tmp_path: Path, store: PostgresStore) -> ContextUse:
    storage = DiskStorage(base_path=str(tmp_path / "storage"))
    return ContextUse(storage=storage, store=store)

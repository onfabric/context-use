import datetime
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import inspect, text

from context_use.db.postgres import PostgresBackend
from context_use.etl.models.archive import Archive, ArchiveStatus
from context_use.etl.models.base import Base
from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.etl.models.thread import Thread
from tests.conftest import Settings


async def _make_db(settings: Settings) -> PostgresBackend:
    db = PostgresBackend(
        host=settings.host,
        port=settings.port,
        database=settings.database,
        user=settings.user,
        password=settings.password,
    )
    await db.init_db()
    return db


@pytest.fixture(autouse=True)
async def _clean_tables(settings: Settings) -> AsyncGenerator[None]:
    db = await _make_db(settings)
    yield
    async with db.session_scope() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())


class TestPostgresBackend:
    async def test_init_creates_tables(self, settings: Settings):
        db = await _make_db(settings)
        engine = db.get_engine()
        async with engine.connect() as conn:
            tables = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )
        assert "archives" in tables
        assert "etl_tasks" in tables
        assert "threads" in tables

    async def test_vector_extension_enabled(self, settings: Settings):
        db = await _make_db(settings)
        async with db.session_scope() as s:
            row = (
                await s.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                )
            ).one_or_none()
            assert row is not None, "pgvector extension is not enabled"

    async def test_archive_crud(self, settings: Settings):
        db = await _make_db(settings)
        async with db.session_scope() as s:
            a = Archive(provider="chatgpt", status=ArchiveStatus.CREATED.value)
            s.add(a)
            await s.flush()
            aid = a.id

        async with db.session_scope() as s:
            row = await s.get(Archive, aid)
            assert row is not None
            assert row.provider == "chatgpt"
            assert row.status == "created"

    async def test_etl_task_crud(self, settings: Settings):
        db = await _make_db(settings)
        async with db.session_scope() as s:
            a = Archive(provider="chatgpt", status=ArchiveStatus.CREATED.value)
            s.add(a)
            await s.flush()

            t = EtlTask(
                archive_id=a.id,
                provider="chatgpt",
                interaction_type="chatgpt_conversations",
                source_uri="conversations.json",
                status=EtlTaskStatus.CREATED.value,
            )
            s.add(t)
            await s.flush()
            tid = t.id

        async with db.session_scope() as s:
            row = await s.get(EtlTask, tid)
            assert row is not None
            assert row.interaction_type == "chatgpt_conversations"

    async def test_thread_crud(self, settings: Settings):
        db = await _make_db(settings)
        async with db.session_scope() as s:
            t = Thread(
                unique_key="test:key",
                provider="chatgpt",
                interaction_type="chatgpt_conversations",
                preview="hello",
                payload={"type": "Create"},
                version="1.0.0",
                asat=datetime.datetime.now(datetime.UTC),
            )
            s.add(t)
            await s.flush()
            tid = t.id

        async with db.session_scope() as s:
            row = await s.get(Thread, tid)
            assert row is not None
            assert row.unique_key == "test:key"
            assert row.payload == {"type": "Create"}

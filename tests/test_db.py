import datetime
from collections.abc import Generator

import pytest
from sqlalchemy import inspect, text

from context_use.db.postgres import PostgresBackend
from context_use.etl.models.archive import Archive, ArchiveStatus
from context_use.etl.models.base import Base
from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.etl.models.thread import Thread
from tests.conftest import Settings


def _make_db(settings: Settings) -> PostgresBackend:
    db = PostgresBackend(
        host=settings.host,
        port=settings.port,
        database=settings.database,
        user=settings.user,
        password=settings.password,
    )
    db.init_db()
    return db


@pytest.fixture(autouse=True)
def _clean_tables(settings: Settings) -> Generator[None]:
    db = _make_db(settings)
    yield
    with db.session_scope() as session:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())


class TestPostgresBackend:
    def test_init_creates_tables(self, settings: Settings):
        db = _make_db(settings)
        inspector = inspect(db.get_engine())
        tables = inspector.get_table_names()
        assert "archives" in tables
        assert "etl_tasks" in tables
        assert "threads" in tables

    def test_vector_extension_enabled(self, settings: Settings):
        db = _make_db(settings)
        with db.session_scope() as s:
            row = s.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).one_or_none()
            assert row is not None, "pgvector extension is not enabled"

    def test_archive_crud(self, settings: Settings):
        db = _make_db(settings)
        with db.session_scope() as s:
            a = Archive(provider="chatgpt", status=ArchiveStatus.CREATED.value)
            s.add(a)
            s.flush()
            aid = a.id

        with db.session_scope() as s:
            row = s.get(Archive, aid)
            assert row is not None
            assert row.provider == "chatgpt"
            assert row.status == "created"

    def test_etl_task_crud(self, settings: Settings):
        db = _make_db(settings)
        with db.session_scope() as s:
            a = Archive(provider="chatgpt", status=ArchiveStatus.CREATED.value)
            s.add(a)
            s.flush()

            t = EtlTask(
                archive_id=a.id,
                provider="chatgpt",
                interaction_type="chatgpt_conversations",
                source_uri="conversations.json",
                status=EtlTaskStatus.CREATED.value,
            )
            s.add(t)
            s.flush()
            tid = t.id

        with db.session_scope() as s:
            row = s.get(EtlTask, tid)
            assert row is not None
            assert row.interaction_type == "chatgpt_conversations"

    def test_thread_crud(self, settings: Settings):
        db = _make_db(settings)
        with db.session_scope() as s:
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
            s.flush()
            tid = t.id

        with db.session_scope() as s:
            row = s.get(Thread, tid)
            assert row is not None
            assert row.unique_key == "test:key"
            assert row.payload == {"type": "Create"}

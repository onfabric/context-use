import datetime
from collections.abc import Generator

import pytest
from sqlalchemy import inspect

from context_use.db.postgres import PostgresBackend
from context_use.etl.models.archive import Archive, ArchiveStatus
from context_use.etl.models.base import Base
from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.etl.models.thread import Thread


def _make_db() -> PostgresBackend:
    db = PostgresBackend(
        host="localhost",
        port=5432,
        database="context_use_tests",
        user="postgres",
        password="postgres",
    )
    db.init_db()
    return db


@pytest.fixture(autouse=True)
def _clean_tables() -> Generator[None]:
    db = _make_db()
    yield
    with db.session_scope() as session:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())


class TestPostgresBackend:
    def test_init_creates_tables(self):
        db = _make_db()
        inspector = inspect(db.get_engine())
        tables = inspector.get_table_names()
        assert "archives" in tables
        assert "etl_tasks" in tables
        assert "threads" in tables

    def test_archive_crud(self):
        db = _make_db()
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

    def test_etl_task_crud(self):
        db = _make_db()
        with db.session_scope() as s:
            a = Archive(provider="chatgpt", status=ArchiveStatus.CREATED.value)
            s.add(a)
            s.flush()

            t = EtlTask(
                archive_id=a.id,
                provider="chatgpt",
                interaction_type="chatgpt_conversations",
                status=EtlTaskStatus.CREATED.value,
            )
            s.add(t)
            s.flush()
            tid = t.id

        with db.session_scope() as s:
            row = s.get(EtlTask, tid)
            assert row is not None
            assert row.interaction_type == "chatgpt_conversations"

    def test_thread_crud(self):
        db = _make_db()
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

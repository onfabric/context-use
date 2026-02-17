"""Unit tests for SQLite backend + model CRUD."""

from contextuse.db.sqlite import SQLiteBackend
from contextuse.models.archive import Archive, ArchiveStatus
from contextuse.models.etl_task import EtlTask, EtlTaskStatus
from contextuse.models.thread import Thread

import datetime


class TestSQLiteBackend:
    def _make_db(self):
        db = SQLiteBackend(path=":memory:")
        db.init_db()
        return db

    def test_init_creates_tables(self):
        db = self._make_db()
        # Tables should exist
        from sqlalchemy import inspect

        inspector = inspect(db.get_engine())
        tables = inspector.get_table_names()
        assert "archives" in tables
        assert "etl_tasks" in tables
        assert "threads" in tables

    def test_archive_crud(self):
        db = self._make_db()
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
        db = self._make_db()
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
        db = self._make_db()
        with db.session_scope() as s:
            t = Thread(
                unique_key="test:key",
                provider="chatgpt",
                interaction_type="chatgpt_conversations",
                preview="hello",
                payload={"type": "Create"},
                version="1.0.0",
                asat=datetime.datetime.now(datetime.timezone.utc),
            )
            s.add(t)
            s.flush()
            tid = t.id

        with db.session_scope() as s:
            row = s.get(Thread, tid)
            assert row is not None
            assert row.unique_key == "test:key"
            assert row.payload == {"type": "Create"}


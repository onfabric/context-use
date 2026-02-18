from datetime import datetime, UTC

from sqlalchemy import inspect

from context_use.db.sqlite import SQLiteBackend
from context_use.models.archive import Archive, ArchiveStatus
from context_use.models.etl_task import EtlTask, EtlTaskStatus
from context_use.models.thread import Thread


def _make_db() -> SQLiteBackend:
    db = SQLiteBackend(":memory:")
    db.init_db()
    return db


class TestInitDB:
    def test_init_creates_tables(self):
        db = _make_db()
        inspector = inspect(db.get_engine())
        table_names = inspector.get_table_names()
        assert "archives" in table_names
        assert "etl_tasks" in table_names
        assert "threads" in table_names


class TestArchiveCRUD:
    def test_create_and_read(self):
        db = _make_db()
        with db.session_scope() as session:
            archive = Archive(provider="chatgpt")
            session.add(archive)
            session.flush()
            archive_id = archive.id

        with db.session_scope() as session:
            loaded = session.get(Archive, archive_id)
            assert loaded is not None
            assert loaded.provider == "chatgpt"
            assert loaded.status == ArchiveStatus.CREATED


class TestEtlTaskCRUD:
    def test_create_and_read(self):
        db = _make_db()
        with db.session_scope() as session:
            archive = Archive(provider="instagram")
            session.add(archive)
            session.flush()

            task = EtlTask(
                archive_id=archive.id,
                provider="instagram",
                interaction_type="stories",
            )
            session.add(task)
            session.flush()
            task_id = task.id

        with db.session_scope() as session:
            loaded = session.get(EtlTask, task_id)
            assert loaded is not None
            assert loaded.interaction_type == "stories"
            assert loaded.status == EtlTaskStatus.CREATED
            assert loaded.extracted_count == 0


class TestThreadCRUD:
    def test_create_and_read(self):
        db = _make_db()
        now = datetime.now(UTC)
        payload = {"type": "Create", "object": {"type": "Note", "content": "hi"}}

        with db.session_scope() as session:
            thread = Thread(
                unique_key="abc123",
                provider="chatgpt",
                interaction_type="conversations",
                preview="hi",
                payload=payload,
                version="1.0.0",
                asat=now,
            )
            session.add(thread)
            session.flush()
            thread_id = thread.id

        with db.session_scope() as session:
            loaded = session.get(Thread, thread_id)
            assert loaded is not None
            assert loaded.unique_key == "abc123"
            assert loaded.payload == payload
            assert loaded.asat is not None

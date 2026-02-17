"""End-to-end test: ChatGPT zip → Thread rows in SQLite."""

from contextuse import ContextUse
from contextuse.models.archive import ArchiveStatus
from contextuse.models.etl_task import EtlTaskStatus
from contextuse.models.thread import Thread
from contextuse.providers.registry import Provider


class TestE2EChatGPT:
    def test_full_flow(self, ctx: ContextUse, chatgpt_zip):
        result = ctx.process_archive(Provider.CHATGPT, str(chatgpt_zip))

        # Should complete without errors
        assert result.tasks_completed == 1
        assert result.tasks_failed == 0
        assert result.threads_created > 0
        assert len(result.errors) == 0

        # Verify DB state
        with ctx._db.session_scope() as s:
            from contextuse.models.archive import Archive
            from contextuse.models.etl_task import EtlTask

            archive = s.get(Archive, result.archive_id)
            assert archive.status == ArchiveStatus.COMPLETED.value
            assert archive.provider == "chatgpt"

            tasks = s.query(EtlTask).filter_by(archive_id=result.archive_id).all()
            assert len(tasks) == 1
            assert tasks[0].interaction_type == "chatgpt_conversations"
            assert tasks[0].status == EtlTaskStatus.COMPLETED.value
            assert tasks[0].uploaded_count > 0

            threads = s.query(Thread).all()
            assert len(threads) == result.threads_created
            for thread in threads:
                assert thread.provider == "chatgpt"
                assert thread.interaction_type == "chatgpt_conversations"
                assert thread.preview
                assert thread.payload
                assert thread.unique_key


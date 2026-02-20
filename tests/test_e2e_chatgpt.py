from sqlalchemy import select

from context_use import ContextUse
from context_use.etl.models.archive import Archive, ArchiveStatus
from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.etl.models.thread import Thread
from context_use.etl.providers.registry import Provider


class TestE2EChatGPT:
    async def test_full_flow(self, ctx: ContextUse, chatgpt_zip):
        result = await ctx.process_archive(Provider.CHATGPT, str(chatgpt_zip))

        # Should complete without errors
        assert result.tasks_completed == 1
        assert result.tasks_failed == 0
        assert result.threads_created > 0
        assert len(result.errors) == 0

        # Verify DB state
        async with ctx._db.session_scope() as s:
            archive = await s.get(Archive, result.archive_id)
            assert archive is not None
            assert archive.status == ArchiveStatus.COMPLETED.value
            assert archive.provider == "chatgpt"

            task_result = await s.execute(
                select(EtlTask).where(EtlTask.archive_id == result.archive_id)
            )
            tasks = task_result.scalars().all()
            assert len(tasks) == 1
            assert tasks[0].interaction_type == "chatgpt_conversations"
            assert tasks[0].status == EtlTaskStatus.COMPLETED.value
            assert tasks[0].uploaded_count > 0
            assert tasks[0].extracted_count > 0
            assert tasks[0].transformed_count > 0
            assert tasks[0].extracted_count >= tasks[0].transformed_count

            thread_result = await s.execute(select(Thread))
            threads = thread_result.scalars().all()
            assert len(threads) == result.threads_created
            for thread in threads:
                assert thread.provider == "chatgpt"
                assert thread.interaction_type == "chatgpt_conversations"
                assert thread.preview
                assert thread.payload
                assert thread.unique_key

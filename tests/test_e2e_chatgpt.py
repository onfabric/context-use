from context_use import ContextUse
from context_use.models.archive import ArchiveStatus
from context_use.models.etl_task import EtlTaskStatus
from context_use.providers.registry import Provider


class TestE2EChatGPT:
    async def test_full_flow(self, ctx: ContextUse, chatgpt_zip):
        result = await ctx.process_archive(Provider.CHATGPT, str(chatgpt_zip))

        assert result.tasks_completed == 1
        assert result.tasks_failed == 0
        assert result.threads_created > 0
        assert len(result.errors) == 0

        archive = await ctx._store.get_archive(result.archive_id)
        assert archive is not None
        assert archive.status == ArchiveStatus.COMPLETED.value
        assert archive.provider == "chatgpt"

        tasks = await ctx._store.get_tasks_by_archive([result.archive_id])
        assert len(tasks) == 1
        assert tasks[0].interaction_type == "chatgpt_conversations"
        assert tasks[0].status == EtlTaskStatus.COMPLETED.value
        assert tasks[0].uploaded_count > 0
        assert tasks[0].extracted_count > 0
        assert tasks[0].transformed_count > 0
        assert tasks[0].extracted_count >= tasks[0].transformed_count

        threads = await ctx._store.get_threads_by_task([tasks[0].id])
        assert len(threads) == result.threads_created
        for thread in threads:
            assert thread.provider == "chatgpt"
            assert thread.interaction_type == "chatgpt_conversations"
            assert thread.preview
            assert thread.payload
            assert thread.unique_key

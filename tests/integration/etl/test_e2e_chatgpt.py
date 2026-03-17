import pytest

from context_use import ContextUse
from context_use.models.archive import ArchiveStatus
from context_use.models.etl_task import EtlTaskStatus
from context_use.providers import chatgpt

pytestmark = pytest.mark.integration


class TestE2EChatGPT:
    async def test_full_flow(self, ctx: ContextUse, chatgpt_zip):
        result = await ctx.process_archive(chatgpt.PROVIDER, str(chatgpt_zip))

        assert result.tasks_completed == 1
        assert result.tasks_failed == 0
        assert result.threads_created > 0
        assert len(result.errors) == 0

        archive = await ctx._store.get_archive(result.archive_id)
        assert archive is not None
        assert archive.status == ArchiveStatus.COMPLETED.value
        assert archive.provider == "chatgpt"

        assert len(result.breakdown) == 1
        breakdown = result.breakdown[0]
        assert breakdown.interaction_type == "chatgpt_conversations"

        task = await ctx._store.get_task(breakdown.task_id)
        assert task is not None
        assert task.status == EtlTaskStatus.COMPLETED.value
        assert task.uploaded_count > 0
        assert task.extracted_count > 0
        assert task.transformed_count > 0
        assert task.extracted_count >= task.transformed_count

        threads = await ctx._store.get_unprocessed_threads()
        assert len(threads) == result.threads_created
        for thread in threads:
            assert thread.provider == "chatgpt"
            assert thread.interaction_type == "chatgpt_conversations"
            assert thread.preview
            assert thread.payload
            assert thread.unique_key

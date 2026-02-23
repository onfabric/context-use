from context_use import ContextUse
from context_use.models.archive import ArchiveStatus
from context_use.models.etl_task import EtlTaskStatus
from context_use.providers.registry import Provider


class TestE2EInstagram:
    async def test_full_flow(self, ctx: ContextUse, instagram_zip):
        result = await ctx.process_archive(Provider.INSTAGRAM, str(instagram_zip))

        assert result.tasks_completed == 2
        assert result.tasks_failed == 0
        assert result.threads_created > 0
        assert len(result.errors) == 0

        archive = await ctx._store.get_archive(result.archive_id)
        assert archive is not None
        assert archive.status == ArchiveStatus.COMPLETED.value

        tasks = await ctx._store.get_tasks_by_archive([result.archive_id])
        interaction_types = {t.interaction_type for t in tasks}
        assert "instagram_stories" in interaction_types
        assert "instagram_reels" in interaction_types

        for t in tasks:
            assert t.status == EtlTaskStatus.COMPLETED.value

        task_ids = [t.id for t in tasks]
        threads = await ctx._store.get_threads_by_task(task_ids)
        assert len(threads) == result.threads_created

        thread_types = {t.interaction_type for t in threads}
        assert "instagram_stories" in thread_types
        assert "instagram_reels" in thread_types

        for thread in threads:
            assert thread.asset_uri is not None
            assert thread.asset_uri.startswith(result.archive_id)
            assert "media/" in thread.asset_uri

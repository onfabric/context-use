from sqlalchemy import select

from context_use import ContextUse
from context_use.etl.models.archive import Archive, ArchiveStatus
from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.etl.models.thread import Thread
from context_use.providers.registry import Provider


class TestE2EInstagram:
    async def test_full_flow(self, ctx: ContextUse, instagram_zip):
        result = await ctx.process_archive(Provider.INSTAGRAM, str(instagram_zip))

        # Should complete both stories and reels tasks
        assert result.tasks_completed == 2
        assert result.tasks_failed == 0
        assert result.threads_created > 0
        assert len(result.errors) == 0

        # Verify DB state
        async with ctx._db.session_scope() as s:
            archive = await s.get(Archive, result.archive_id)
            assert archive is not None
            assert archive.status == ArchiveStatus.COMPLETED.value

            task_result = await s.execute(
                select(EtlTask).where(EtlTask.archive_id == result.archive_id)
            )
            tasks = task_result.scalars().all()
            interaction_types = {t.interaction_type for t in tasks}
            assert "instagram_stories" in interaction_types
            assert "instagram_reels" in interaction_types

            for t in tasks:
                assert t.status == EtlTaskStatus.COMPLETED.value

            thread_result = await s.execute(select(Thread))
            threads = thread_result.scalars().all()
            assert len(threads) == result.threads_created

            thread_types = {t.interaction_type for t in threads}
            assert "instagram_stories" in thread_types
            assert "instagram_reels" in thread_types

            # All threads should have asset_uri as full storage keys
            for thread in threads:
                assert thread.asset_uri is not None
                assert thread.asset_uri.startswith(result.archive_id)
                assert "media/" in thread.asset_uri

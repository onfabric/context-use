"""End-to-end test: Instagram zip → Thread rows in SQLite."""

from context_use import ContextUse
from context_use.etl.models.archive import Archive, ArchiveStatus
from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.etl.models.thread import Thread
from context_use.etl.providers.registry import Provider


class TestE2EInstagram:
    def test_full_flow(self, ctx: ContextUse, instagram_zip):
        result = ctx.process_archive(Provider.INSTAGRAM, str(instagram_zip))

        # Should complete both stories and reels tasks
        assert result.tasks_completed == 2
        assert result.tasks_failed == 0
        assert result.threads_created > 0
        assert len(result.errors) == 0

        # Verify DB state
        with ctx._db.session_scope() as s:
            archive = s.get(Archive, result.archive_id)
            assert archive.status == ArchiveStatus.COMPLETED.value

            tasks = s.query(EtlTask).filter_by(archive_id=result.archive_id).all()
            interaction_types = {t.interaction_type for t in tasks}
            assert "instagram_stories" in interaction_types
            assert "instagram_reels" in interaction_types

            for t in tasks:
                assert t.status == EtlTaskStatus.COMPLETED.value

            threads = s.query(Thread).all()
            assert len(threads) == result.threads_created

            # Check that stories and reels produced threads
            thread_types = {t.interaction_type for t in threads}
            assert "instagram_stories" in thread_types
            assert "instagram_reels" in thread_types

            # All threads should have asset_uri
            for thread in threads:
                assert thread.asset_uri is not None
                assert "media/" in thread.asset_uri

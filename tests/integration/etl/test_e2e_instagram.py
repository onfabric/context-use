from context_use import ContextUse
from context_use.models.archive import ArchiveStatus

# Interaction types that produce threads with asset_uri
_MEDIA_TYPES = {"instagram_stories", "instagram_reels"}


class TestE2EInstagram:
    async def test_full_flow(self, ctx: ContextUse, instagram_zip):
        result = await ctx.process_archive("instagram", str(instagram_zip))

        assert result.tasks_completed >= 10
        assert result.tasks_failed == 0
        assert result.threads_created > 0
        assert len(result.errors) == 0

        archive = await ctx._store.get_archive(result.archive_id)
        assert archive is not None
        assert archive.status == ArchiveStatus.COMPLETED.value

        interaction_types = {b.interaction_type for b in result.breakdown}
        assert "instagram_stories" in interaction_types
        assert "instagram_reels" in interaction_types
        assert "instagram_liked_posts" in interaction_types
        assert "instagram_followers" in interaction_types
        assert "instagram_following" in interaction_types
        assert "instagram_comments_posts" in interaction_types
        assert "instagram_saved_posts" in interaction_types
        assert "instagram_saved_collections" in interaction_types

        threads = await ctx._store.get_unprocessed_threads()
        assert len(threads) == result.threads_created

        thread_types = {t.interaction_type for t in threads}
        assert "instagram_stories" in thread_types
        assert "instagram_reels" in thread_types

        for thread in threads:
            if thread.interaction_type in _MEDIA_TYPES:
                assert thread.asset_uri is not None
                assert thread.asset_uri.startswith(result.archive_id)
                assert "media/" in thread.asset_uri

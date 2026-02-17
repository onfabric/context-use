"""Instagram orchestration strategy."""

from __future__ import annotations

from contextuse.core.etl import OrchestrationStrategy


class InstagramOrchestrationStrategy(OrchestrationStrategy):
    """Discovers Instagram ETL tasks from extracted archive files.

    Looks for manifest JSONs under ``your_instagram_activity/media/``.
    """

    MANIFEST_MAP = {
        "your_instagram_activity/media/stories.json": "instagram_stories",
        "your_instagram_activity/media/reels.json": "instagram_reels",
    }


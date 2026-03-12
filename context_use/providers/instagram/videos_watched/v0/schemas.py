from __future__ import annotations

from context_use.providers.instagram.schemas import (
    InstagramAuthorSchema,
    InstagramBaseModel,
    InstagramStringMapDataWrapper,
)


class InstagramVideosWatchedManifest(InstagramBaseModel):
    impressions_history_videos_watched: list[
        InstagramStringMapDataWrapper[InstagramAuthorSchema]
    ]

from __future__ import annotations

from context_use.providers.instagram.schemas import (
    InstagramAuthorSchema,
    InstagramBaseModel,
    InstagramStringMapDataWrapper,
)


class InstagramVideosWatchedV0Manifest(InstagramBaseModel):
    impressions_history_videos_watched: list[
        InstagramStringMapDataWrapper[InstagramAuthorSchema]
    ]

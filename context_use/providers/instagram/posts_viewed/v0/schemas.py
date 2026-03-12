from __future__ import annotations

from context_use.providers.instagram.schemas import (
    InstagramAuthorSchema,
    InstagramBaseModel,
    InstagramStringMapDataWrapper,
)


class InstagramPostsViewedManifest(InstagramBaseModel):
    impressions_history_posts_seen: list[
        InstagramStringMapDataWrapper[InstagramAuthorSchema]
    ]

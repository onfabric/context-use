from __future__ import annotations

from context_use.providers.instagram.schemas import (
    InstagramAuthorSchema,
    InstagramBaseModel,
    InstagramStringMapDataWrapper,
)


class InstagramPostsViewedV0Manifest(InstagramBaseModel):
    impressions_history_posts_seen: list[
        InstagramStringMapDataWrapper[InstagramAuthorSchema]
    ]

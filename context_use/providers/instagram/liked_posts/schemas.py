from __future__ import annotations

from context_use.providers.instagram.schemas import (
    InstagramBaseModel,
    InstagramHrefTimestampSchema,
)


class InstagramV0LikesItem(InstagramBaseModel):
    title: str = ""
    string_list_data: list[InstagramHrefTimestampSchema]


class InstagramLikedPostsV0Manifest(InstagramBaseModel):
    likes_media_likes: list[InstagramV0LikesItem]

from __future__ import annotations

from context_use.providers.instagram.schemas import (
    InstagramBaseModel,
    InstagramHrefTimestampSchema,
)


class InstagramLikesItem(InstagramBaseModel):
    title: str = ""
    string_list_data: list[InstagramHrefTimestampSchema]


class InstagramLikedPostsManifest(InstagramBaseModel):
    likes_media_likes: list[InstagramLikesItem]


class InstagramStoryLikesManifest(InstagramBaseModel):
    story_activities_story_likes: list[InstagramLikesItem]

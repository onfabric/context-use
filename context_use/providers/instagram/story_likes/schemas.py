from __future__ import annotations

from context_use.providers.instagram.schemas import (
    InstagramBaseModel,
    InstagramHrefTimestampSchema,
)


class InstagramV0StoryLikesItem(InstagramBaseModel):
    title: str = ""
    string_list_data: list[InstagramHrefTimestampSchema]


class InstagramStoryLikesV0Manifest(InstagramBaseModel):
    story_activities_story_likes: list[InstagramV0StoryLikesItem]

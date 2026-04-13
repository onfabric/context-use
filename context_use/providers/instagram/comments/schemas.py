from __future__ import annotations

from pydantic import Field

from context_use.providers.instagram.schemas import (
    InstagramBaseModel,
    InstagramTimestampSchema,
    InstagramValueSchema,
)


class InstagramCommentMediaItem(InstagramBaseModel):
    uri: str


class InstagramCommentStringMapData(InstagramBaseModel):
    Comment: InstagramValueSchema | None = None
    Time: InstagramTimestampSchema
    Media_Owner: InstagramValueSchema | None = Field(None, alias="Media Owner")


class InstagramCommentFileItem(InstagramBaseModel):
    string_map_data: InstagramCommentStringMapData
    media_list_data: list[InstagramCommentMediaItem] = []


class InstagramReelsCommentsManifest(InstagramBaseModel):
    comments_reels_comments: list[InstagramCommentFileItem]

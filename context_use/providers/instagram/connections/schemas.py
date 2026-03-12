from __future__ import annotations

from context_use.providers.instagram.schemas import (
    InstagramBaseModel,
    InstagramHrefTimestampSchema,
)


class InstagramConnectionItem(InstagramBaseModel):
    string_list_data: list[InstagramHrefTimestampSchema]


class InstagramFollowingItem(InstagramBaseModel):
    title: str
    string_list_data: list[InstagramHrefTimestampSchema]


class InstagramFollowingManifest(InstagramBaseModel):
    relationships_following: list[InstagramFollowingItem]

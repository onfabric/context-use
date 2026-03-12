from __future__ import annotations

from context_use.providers.instagram.schemas import (
    InstagramBaseModel,
    InstagramHrefTimestampSchema,
)


class InstagramV0SearchItem(InstagramBaseModel):
    title: str | None = None
    string_list_data: list[InstagramHrefTimestampSchema]


class InstagramProfileSearchesManifest(InstagramBaseModel):
    searches_user: list[InstagramV0SearchItem]

from __future__ import annotations

from pydantic import Field

from context_use.providers.instagram.schemas import InstagramBaseModel


class InstagramSavedOnSchema(InstagramBaseModel):
    href: str | None = None
    timestamp: int | None = None


class InstagramSavedPostSMD(InstagramBaseModel):
    saved_on: InstagramSavedOnSchema = Field(alias="Saved on")


class InstagramSavedPostItem(InstagramBaseModel):
    title: str = ""
    string_map_data: InstagramSavedPostSMD


class InstagramSavedStringMapEntry(InstagramBaseModel):
    value: str | None = None
    href: str | None = None
    timestamp: int | None = None


class InstagramSavedCollectionItem(InstagramBaseModel):
    title: str = ""
    string_map_data: dict[str, InstagramSavedStringMapEntry]


class InstagramSavedPostsManifest(InstagramBaseModel):
    saved_saved_media: list[InstagramSavedPostItem]


class InstagramSavedCollectionsManifest(InstagramBaseModel):
    saved_saved_collections: list[InstagramSavedCollectionItem]

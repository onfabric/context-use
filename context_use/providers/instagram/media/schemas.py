from __future__ import annotations

from context_use.providers.instagram.schemas import InstagramBaseModel


class InstagramMediaItem(InstagramBaseModel):
    uri: str
    creation_timestamp: int
    title: str = ""
    media_metadata: dict | None = None


class InstagramStoriesManifest(InstagramBaseModel):
    ig_stories: list[InstagramMediaItem]


class InstagramReelsEntry(InstagramBaseModel):
    media: list[InstagramMediaItem]


class InstagramReelsManifest(InstagramBaseModel):
    ig_reels_media: list[InstagramReelsEntry]


class InstagramPostsEntry(InstagramBaseModel):
    media: list[InstagramMediaItem]

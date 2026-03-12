from __future__ import annotations

from pydantic import BaseModel


class InstagramMediaItem(BaseModel):
    uri: str
    creation_timestamp: int
    title: str = ""
    media_metadata: dict | None = None


class InstagramStoriesManifest(BaseModel):
    ig_stories: list[InstagramMediaItem]


class InstagramReelsEntry(BaseModel):
    media: list[InstagramMediaItem]


class InstagramReelsManifest(BaseModel):
    ig_reels_media: list[InstagramReelsEntry]


class InstagramPostsEntry(BaseModel):
    media: list[InstagramMediaItem]

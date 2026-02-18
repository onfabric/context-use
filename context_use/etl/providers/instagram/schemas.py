"""Pydantic schemas for the real Instagram archive format."""

from __future__ import annotations

from pydantic import BaseModel


class InstagramMediaItem(BaseModel):
    """A single media item (story frame, reel clip, etc.)."""

    uri: str
    creation_timestamp: int
    title: str = ""
    media_metadata: dict | None = None


class InstagramStoriesManifest(BaseModel):
    """Top-level schema for ``stories.json``."""

    ig_stories: list[InstagramMediaItem]


class InstagramReelsEntry(BaseModel):
    """One reel entry in ``reels.json`` (wraps a list of media clips)."""

    media: list[InstagramMediaItem]


class InstagramReelsManifest(BaseModel):
    """Top-level schema for ``reels.json``."""

    ig_reels_media: list[InstagramReelsEntry]

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


class InstagramMediaRecord(BaseModel):
    """Enriched extraction output for Instagram media (stories, reels, posts).

    Shared across ``instagram_stories``, ``instagram_reels``, and
    (future) ``instagram_posts`` interaction types.
    """

    uri: str
    creation_timestamp: int
    title: str = ""
    media_type: str  # "Image" or "Video", inferred from URI extension
    source: str | None = None

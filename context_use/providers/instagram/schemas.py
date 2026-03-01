from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator

# ---------------------------------------------------------------------------
# Mojibake fix — Instagram encodes UTF-8 bytes as \u00xx Latin-1 codepoints
# ---------------------------------------------------------------------------


def fix_instagram_encoding(text: str) -> str:
    """Fix Instagram's broken UTF-8-as-Latin-1 encoding in JSON exports.

    Instagram's data export encodes UTF-8 bytes as ``\\u00xx`` JSON escapes,
    e.g. the emoji 🙏 (UTF-8: f0 9f 99 8f) becomes ``\\u00f0\\u009f\\u0099\\u008f``.
    Python's JSON parser reads these as Latin-1 codepoints, producing mojibake.

    This re-interprets each character as a Latin-1 byte, then decodes as UTF-8.
    Falls back to the original string if it's already valid UTF-8 or not decodable.
    """
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def _fix_strings_recursive(data: Any) -> Any:
    """Recursively fix all string values in a nested dict/list structure."""
    if isinstance(data, str):
        return fix_instagram_encoding(data)
    if isinstance(data, dict):
        return {k: _fix_strings_recursive(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_fix_strings_recursive(item) for item in data]
    return data


class InstagramBaseModel(BaseModel):
    """Base model for all Instagram data export schemas.

    Automatically fixes Instagram's broken UTF-8 encoding where multi-byte
    characters are stored as individual ``\\u00xx`` Latin-1 codepoints.
    """

    @model_validator(mode="before")
    @classmethod
    def _fix_instagram_mojibake(cls, data: Any) -> Any:
        return _fix_strings_recursive(data)


# ---------------------------------------------------------------------------
# V0 string_map_data helper schemas (used by ads_information pipes)
# ---------------------------------------------------------------------------


class InstagramValueSchema(InstagramBaseModel):
    """A simple ``{"value": "..."}`` wrapper."""

    value: str


class InstagramTimestampSchema(InstagramBaseModel):
    """A simple ``{"timestamp": ...}`` wrapper."""

    timestamp: int


class InstagramAuthorSchema(InstagramBaseModel):
    """``string_map_data`` shape for ads/video items: ``{Author, Time}``."""

    Author: InstagramValueSchema
    Time: InstagramTimestampSchema


class InstagramStringMapDataWrapper[T](InstagramBaseModel):
    """Generic wrapper for v0 items that carry a ``string_map_data`` key."""

    string_map_data: T


# ---------------------------------------------------------------------------
# V1 label_values helper schemas (used by ads_information v1 pipes)
# ---------------------------------------------------------------------------


class InstagramLabelValue(InstagramBaseModel):
    """One entry inside the ``label_values`` array of a v1 item."""

    label: str
    value: str
    href: str | None = None


# ---------------------------------------------------------------------------
# Extracted record — version-independent output of extract()
# ---------------------------------------------------------------------------


class InstagramVideoWatchedRecord(BaseModel):
    """Normalised record for a watched video (v0 and v1 share this)."""

    author: str | None = None
    video_url: str | None = None
    timestamp: int
    source: str | None = None


# ---------------------------------------------------------------------------
# Media schemas (stories, reels, posts)
# ---------------------------------------------------------------------------


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

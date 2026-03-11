from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator

PROVIDER = "instagram"


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
    value: str | None = None
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


# ---------------------------------------------------------------------------
# V1 string_list_data helper schemas (shared across many interaction types)
# ---------------------------------------------------------------------------


class InstagramHrefTimestampSchema(InstagramBaseModel):
    """One entry inside a ``string_list_data`` array.

    Fields ``href`` and ``value`` are optional — some interaction types
    (e.g. story likes) only carry a ``timestamp``.
    """

    href: str | None = None
    value: str | None = None
    timestamp: int


class InstagramStringListDataWrapper[T](InstagramBaseModel):
    """Generic wrapper for items that carry a ``string_list_data`` key."""

    string_list_data: list[T]


# ---------------------------------------------------------------------------
# Extracted records — posts viewed
# ---------------------------------------------------------------------------


class InstagramPostsViewedRecord(BaseModel):
    """Normalised record for a viewed post (v0 and v1 share this)."""

    author: str | None = None
    post_url: str | None = None
    timestamp: int
    source: str | None = None


# ---------------------------------------------------------------------------
# Extracted records — profile searches
# ---------------------------------------------------------------------------


class InstagramProfileSearchRecord(BaseModel):
    """Normalised record for a profile search."""

    username: str | None = None
    href: str | None = None
    timestamp: int
    source: str | None = None


# ---------------------------------------------------------------------------
# Media schemas (stories, reels, posts)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Extracted records — liked posts and story likes
# ---------------------------------------------------------------------------


class InstagramLikedPostRecord(BaseModel):
    """Normalised record for a liked post."""

    title: str
    href: str | None = None
    timestamp: int
    source: str | None = None


class InstagramStoryLikeRecord(BaseModel):
    """Normalised record for a story like."""

    title: str
    timestamp: int
    source: str | None = None


# ---------------------------------------------------------------------------
# Extracted records — comments
# ---------------------------------------------------------------------------


class InstagramCommentSchema(InstagramBaseModel):
    """``string_map_data`` shape for comment items.

    ``{Comment: {value}, "Media Owner": {value}, Time: {timestamp}}``
    """

    Comment: InstagramValueSchema
    Time: InstagramTimestampSchema


class InstagramCommentRecord(BaseModel):
    """Normalised record for a comment on a post or reel."""

    comment: str
    media_owner: str | None = None
    timestamp: int
    source: str | None = None


# ---------------------------------------------------------------------------
# Extracted records — connections (followers / following)
# ---------------------------------------------------------------------------


class InstagramConnectionRecord(BaseModel):
    """Normalised record for a follower or following connection."""

    username: str
    profile_url: str | None = None
    timestamp: int
    source: str | None = None


class InstagramConnectionItem(InstagramBaseModel):
    """One item in a followers JSON array."""

    string_list_data: list[InstagramHrefTimestampSchema]


class InstagramFollowingItem(InstagramBaseModel):
    """One item in the ``relationships_following`` array."""

    title: str
    string_list_data: list[InstagramHrefTimestampSchema]


class InstagramFollowingManifest(InstagramBaseModel):
    """Top-level schema for ``following.json``."""

    relationships_following: list[InstagramFollowingItem]


# ---------------------------------------------------------------------------
# Extracted records — saved posts
# ---------------------------------------------------------------------------


class InstagramSavedPostRecord(BaseModel):
    """Normalised record for a saved post."""

    title: str
    href: str | None = None
    timestamp: int
    source: str | None = None


# ---------------------------------------------------------------------------
# Extracted records — saved collections
# ---------------------------------------------------------------------------


class InstagramSavedCollectionRecord(BaseModel):
    """Normalised record for a post saved to a named collection.

    Each record pairs the collection-level metadata (name, creation time)
    with one child item (post author, href, added time).
    """

    collection_name: str
    collection_created_at: int
    item_author: str
    item_href: str | None = None
    item_added_at: int
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


class InstagramPostsEntry(BaseModel):
    """One post entry in ``posts_*.json`` (wraps a list of media items)."""

    media: list[InstagramMediaItem]


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


class InstagramDirectMessageRecord(BaseModel):
    """Normalised record for one Instagram direct message.

    ``is_inbound`` is inferred.
    """

    sender_name: str
    content: str | None
    link: str | None = None
    share_text: str | None = None
    original_content_owner: str | None = None
    timestamp_ms: int
    thread_path: str
    title: str
    is_inbound: bool
    source: str | None = None

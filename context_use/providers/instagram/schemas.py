from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator

PROVIDER = "instagram"


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
    if isinstance(data, str):
        return fix_instagram_encoding(data)
    if isinstance(data, dict):
        return {k: _fix_strings_recursive(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_fix_strings_recursive(item) for item in data]
    return data


def extract_owner_username(owner_data: dict) -> str | None:
    """Extract the username from the nested Owner dict in v1 label_values.

    The Owner entry looks like::

        {
            "title": "Owner",
            "dict": [
                {
                    "title": "",
                    "dict": [
                        {"label": "Username", "value": "some_user"},
                        {"label": "Name", "value": "Some User"},
                        ...
                    ]
                }
            ]
        }
    """
    for outer in owner_data.get("dict", []):
        for inner in outer.get("dict", []):
            if inner.get("label") == "Username":
                return inner.get("value")
    return None


class InstagramBaseModel(BaseModel):
    """Base model for all Instagram data export schemas.

    Automatically fixes Instagram's broken UTF-8 encoding where multi-byte
    characters are stored as individual ``\\u00xx`` Latin-1 codepoints.
    """

    @model_validator(mode="before")
    @classmethod
    def _fix_instagram_mojibake(cls, data: Any) -> Any:
        return _fix_strings_recursive(data)


class InstagramValueSchema(InstagramBaseModel):
    value: str


class InstagramTimestampSchema(InstagramBaseModel):
    timestamp: int


class InstagramAuthorSchema(InstagramBaseModel):
    Author: InstagramValueSchema
    Time: InstagramTimestampSchema


class InstagramStringMapDataWrapper[T](InstagramBaseModel):
    string_map_data: T


class InstagramLabelValue(InstagramBaseModel):
    label: str
    value: str | None = None
    href: str | None = None


class InstagramVideoWatchedRecord(BaseModel):
    author: str | None = None
    video_url: str | None = None
    timestamp: int
    source: str | None = None


class InstagramHrefTimestampSchema(InstagramBaseModel):
    href: str | None = None
    value: str | None = None
    timestamp: int


class InstagramStringListDataWrapper[T](InstagramBaseModel):
    string_list_data: list[T]


class InstagramPostsViewedRecord(BaseModel):
    author: str | None = None
    post_url: str | None = None
    timestamp: int
    source: str | None = None


class InstagramProfileSearchRecord(BaseModel):
    username: str | None = None
    href: str | None = None
    timestamp: int
    source: str | None = None


class InstagramLikedPostRecord(BaseModel):
    title: str
    href: str | None = None
    timestamp: int
    source: str | None = None


class InstagramCommentRecord(BaseModel):
    comment: str
    media_owner: str | None = None
    timestamp: int
    source: str | None = None


class InstagramConnectionRecord(BaseModel):
    username: str
    profile_url: str | None = None
    timestamp: int
    source: str | None = None


class InstagramConnectionItem(InstagramBaseModel):
    string_list_data: list[InstagramHrefTimestampSchema]


class InstagramFollowingItem(InstagramBaseModel):
    title: str
    string_list_data: list[InstagramHrefTimestampSchema]


class InstagramFollowingManifest(InstagramBaseModel):
    relationships_following: list[InstagramFollowingItem]


class InstagramSavedPostRecord(BaseModel):
    title: str
    href: str | None = None
    timestamp: int
    source: str | None = None


class InstagramSavedCollectionRecord(BaseModel):
    collection_name: str
    collection_created_at: int
    item_author: str
    item_href: str | None = None
    item_added_at: int
    source: str | None = None


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


class InstagramMediaRecord(BaseModel):
    uri: str
    creation_timestamp: int
    title: str = ""
    source: str | None = None


class InstagramDMShare(InstagramBaseModel):
    link: str | None = None
    share_text: str | None = None
    original_content_owner: str | None = None


class InstagramDMMessage(InstagramBaseModel):
    sender_name: str
    timestamp_ms: int
    content: str | None = None
    share: InstagramDMShare | None = None


class InstagramDMFile(InstagramBaseModel):
    thread_path: str
    title: str
    messages: list[InstagramDMMessage]


class InstagramDirectMessageRecord(BaseModel):
    sender_name: str
    content: str | None
    link: str | None = None
    share_text: str | None = None
    original_content_owner: str | None = None
    timestamp_ms: int
    thread_path: str
    title: str
    source: str | None = None

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

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


def extract_owner_username(owner_entry: InstagramV1OwnerEntry) -> str | None:
    for group in owner_entry.entries:
        for entry in group.entries:
            if entry.label == "Username":
                return entry.value
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


class InstagramV1OwnerInnerGroup(InstagramBaseModel):
    title: str = ""
    entries: list[InstagramLabelValue] = Field(alias="dict")


class InstagramV1OwnerEntry(InstagramBaseModel):
    title: str
    entries: list[InstagramV1OwnerInnerGroup] = Field(alias="dict")


class InstagramV1ActivityItem(InstagramBaseModel):
    timestamp: int
    label_values: list[InstagramLabelValue | InstagramV1OwnerEntry] = []


class InstagramHrefTimestampSchema(InstagramBaseModel):
    href: str | None = None
    value: str | None = None
    timestamp: int


class InstagramStringListDataWrapper[T](InstagramBaseModel):
    string_list_data: list[T]

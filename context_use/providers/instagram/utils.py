from __future__ import annotations

from typing import Any

from context_use.providers.instagram.schemas import LabelValue

PROVIDER = "instagram"


def fix_instagram_encoding(text: str) -> str:
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def fix_strings_recursive(data: Any) -> Any:
    if isinstance(data, str):
        return fix_instagram_encoding(data)
    if isinstance(data, dict):
        return {k: fix_strings_recursive(v) for k, v in data.items()}
    if isinstance(data, list):
        return [fix_strings_recursive(item) for item in data]
    return data


def extract_owner_username(lv: LabelValue) -> str | None:
    if not lv.dict_ or lv.title != "Owner":
        return None
    for group in lv.dict_:
        for entry in group.dict_:
            if entry.label == "Username":
                return entry.value
    return None

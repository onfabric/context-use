from __future__ import annotations

from context_use.providers.instagram.schemas import InstagramBaseModel


class InstagramDirectMessageShare(InstagramBaseModel):
    link: str | None = None
    share_text: str | None = None
    original_content_owner: str | None = None


class InstagramDirectMessageItem(InstagramBaseModel):
    sender_name: str
    timestamp_ms: int
    content: str | None = None
    share: InstagramDirectMessageShare | None = None


class InstagramDirectMessageManifest(InstagramBaseModel):
    thread_path: str
    title: str
    messages: list[InstagramDirectMessageItem]

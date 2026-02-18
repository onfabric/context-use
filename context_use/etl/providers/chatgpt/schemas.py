"""Pydantic schemas for raw ChatGPT archive data."""

from __future__ import annotations

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Raw archive schemas (model the nested JSON inside conversations.json)
# ---------------------------------------------------------------------------


class ChatGPTAuthor(BaseModel):
    role: str


class ChatGPTContent(BaseModel):
    content_type: str | None = None
    parts: list[str] | None = None


class ChatGPTMessage(BaseModel):
    author: ChatGPTAuthor
    content: ChatGPTContent
    create_time: float | None = None


# ---------------------------------------------------------------------------
# Extraction output record (E→T contract)
# ---------------------------------------------------------------------------


class ChatGPTConversationRecord(BaseModel):
    """Enriched extraction output for ChatGPT conversations.

    Flattened from the nested ``ChatGPTMessage`` structure with
    conversation-level context (id, title) added by extraction.
    """

    role: str
    content: str
    create_time: float | None = None
    conversation_id: str | None = None
    conversation_title: str | None = None
    source: str | None = None

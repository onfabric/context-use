"""Pydantic schemas for raw ChatGPT archive data."""

from __future__ import annotations

from pydantic import BaseModel


class ChatGPTAuthor(BaseModel):
    role: str


class ChatGPTContent(BaseModel):
    content_type: str | None = None
    parts: list[str] | None = None


class ChatGPTMessage(BaseModel):
    author: ChatGPTAuthor
    content: ChatGPTContent
    create_time: float | None = None

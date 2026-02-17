"""Pydantic schemas for raw ChatGPT archive data."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ChatGPTAuthor(BaseModel):
    role: str


class ChatGPTContent(BaseModel):
    content_type: Optional[str] = None
    parts: Optional[list[str]] = None


class ChatGPTMessage(BaseModel):
    author: ChatGPTAuthor
    content: ChatGPTContent
    create_time: Optional[float] = None


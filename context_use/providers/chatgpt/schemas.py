from __future__ import annotations

from pydantic import BaseModel

PROVIDER = "chatgpt"


class ChatGPTAuthor(BaseModel):
    role: str


class ChatGPTContent(BaseModel):
    content_type: str | None = None
    parts: list[str | dict[str, object]] | None = None


class ChatGPTMessage(BaseModel):
    author: ChatGPTAuthor
    content: ChatGPTContent
    create_time: float | None = None


class ChatGPTMappingNode(BaseModel):
    message: ChatGPTMessage | None = None


class ChatGPTConversation(BaseModel):
    title: str | None = None
    conversation_id: str | None = None
    mapping: dict[str, ChatGPTMappingNode]


class ChatGPTConversationRecord(BaseModel):
    role: str
    content: str
    create_time: float | None = None
    conversation_id: str | None = None
    conversation_title: str | None = None
    source: str | None = None

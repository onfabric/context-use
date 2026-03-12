from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

PROVIDER = "chatgpt"


class ChatGPTRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatGPTAuthor(BaseModel):
    role: str


class ChatGPTContent(BaseModel):
    content_type: str | None = None
    parts: list[str | dict[str, object]] | None = None


class ChatGPTMessage(BaseModel):
    author: ChatGPTAuthor
    content: ChatGPTContent
    create_time: float | None = None

    @property
    def is_emittable(self) -> bool:
        return self.content.content_type == "text" and self.author.role in ChatGPTRole


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

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from enum import StrEnum

import ijson

from context_use.batch.grouper import CollectionGrouper
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    Application,
    Collection,
    FibreReceiveMessage,
    FibreSendMessage,
    FibreTextMessage,
)
from context_use.memories.config import MemoryConfig
from context_use.memories.prompt.conversation import (
    AgentConversationMemoryPromptBuilder,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.chatgpt.conversations.record import (
    ChatGPTConversationRecord,
)
from context_use.providers.chatgpt.conversations.schemas import Model
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)

PROVIDER = "chatgpt"

_TEXT_CONTENT_TYPE = "text"


class ChatGPTRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


CHATGPT_APPLICATION = Application(name="assistant")  # type: ignore[reportCallIssue]


def _parse_timestamp(ts: float | None) -> datetime | None:
    return datetime.fromtimestamp(ts, tz=UTC) if ts is not None else None


def _build_payload(
    record: ChatGPTConversationRecord,
) -> FibreSendMessage | FibreReceiveMessage | None:
    context = None
    if record.conversation_title or record.conversation_id:
        ctx_kwargs: dict = {"type": "Collection"}
        if record.conversation_title:
            ctx_kwargs["name"] = record.conversation_title
        if record.conversation_id:
            ctx_kwargs["id"] = f"https://chatgpt.com/c/{record.conversation_id}"
        context = Collection(**ctx_kwargs)

    message = FibreTextMessage(content=record.content, context=context)  # type: ignore[reportCallIssue]

    published = _parse_timestamp(record.create_time)

    if record.role == ChatGPTRole.USER:
        return FibreSendMessage(  # type: ignore[reportCallIssue]
            object=message,
            target=CHATGPT_APPLICATION,
            published=published,
        )
    elif record.role == ChatGPTRole.ASSISTANT:
        return FibreReceiveMessage(  # type: ignore[reportCallIssue]
            object=message,
            actor=CHATGPT_APPLICATION,
            published=published,
        )

    return None


class ChatGPTConversationsPipe(Pipe[ChatGPTConversationRecord]):
    provider = PROVIDER
    interaction_type = "chatgpt_conversations"
    archive_version = 1
    archive_path_pattern = "conversations*.json"
    record_schema = ChatGPTConversationRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[ChatGPTConversationRecord]:
        stream = storage.open_stream(source_uri)

        try:
            for conversation in self._validated_items(
                ijson.items(stream, "item"), Model
            ):
                for _node_id, node in conversation.mapping.items():
                    message = node.message
                    if message is None:
                        continue
                    if (
                        message.content.content_type != _TEXT_CONTENT_TYPE
                        or message.author.role not in ChatGPTRole
                    ):
                        continue
                    if not message.content.parts:
                        continue
                    part = message.content.parts[0]
                    if not isinstance(part, str) or not part.strip():
                        continue

                    yield ChatGPTConversationRecord(
                        role=message.author.role,
                        content=part,
                        create_time=message.create_time,
                        conversation_id=conversation.conversation_id,
                        conversation_title=conversation.title,
                        source=json.dumps(message.model_dump(), default=str),
                    )
        finally:
            stream.close()

    def transform(
        self,
        record: ChatGPTConversationRecord,
        task: EtlTask,
    ) -> ThreadRow:
        payload = _build_payload(record)
        assert payload is not None, (
            f"Unexpected None payload for role={record.role!r}; "
            "extract() should have filtered this record"
        )

        asat = _parse_timestamp(record.create_time) or datetime.now(UTC)

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview("ChatGPT") or "",
            payload=payload.to_dict(),
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=asat,
            source=record.source,
            collection_id=payload.get_collection(),
        )


declare_interaction(
    InteractionConfig(
        pipe=ChatGPTConversationsPipe,
        memory=MemoryConfig(
            prompt_builder=AgentConversationMemoryPromptBuilder,
            grouper=CollectionGrouper,
        ),
    )
)

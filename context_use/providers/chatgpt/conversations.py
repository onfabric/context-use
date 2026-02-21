from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import ijson

from context_use.batch.grouper import CollectionGrouper
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.models.etl_task import EtlTask
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    Application,
    Collection,
    FibreReceiveMessage,
    FibreSendMessage,
    FibreTextMessage,
)
from context_use.memories.config import MemoryConfig
from context_use.memories.prompt.conversation import ConversationMemoryPromptBuilder
from context_use.providers.chatgpt.schemas import (
    ChatGPTConversationRecord,
    ChatGPTMessage,
)
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)

CHATGPT_APPLICATION = Application(name="assistant")  # type: ignore[reportCallIssue]

# Timestamps above this threshold are treated as milliseconds (year 2100+)
_MAX_SECONDS_EPOCH = 4_102_444_800  # 2100-01-01 00:00 UTC


def _safe_timestamp(ts: float | int | None) -> datetime | None:
    """Convert a Unix epoch to datetime, handling ms-vs-s ambiguity."""
    if ts is None:
        return None
    ts = float(ts)
    if ts > _MAX_SECONDS_EPOCH:
        ts /= 1000.0
    return datetime.fromtimestamp(ts, tz=UTC)


def _build_payload(
    record: ChatGPTConversationRecord,
) -> FibreSendMessage | FibreReceiveMessage | None:
    """Build an ActivityStreams payload from a conversation record."""
    # Build conversation context
    context = None
    if record.conversation_title or record.conversation_id:
        ctx_kwargs: dict = {"type": "Collection"}
        if record.conversation_title:
            ctx_kwargs["name"] = record.conversation_title
        if record.conversation_id:
            ctx_kwargs["id"] = f"https://chatgpt.com/c/{record.conversation_id}"
        context = Collection(**ctx_kwargs)

    message = FibreTextMessage(content=record.content, context=context)  # type: ignore[reportCallIssue]

    published = _safe_timestamp(record.create_time)

    if record.role == "user":
        return FibreSendMessage(  # type: ignore[reportCallIssue]
            object=message,
            target=CHATGPT_APPLICATION,
            published=published,
        )
    elif record.role == "assistant":
        return FibreReceiveMessage(  # type: ignore[reportCallIssue]
            object=message,
            actor=CHATGPT_APPLICATION,
            published=published,
        )

    return None


class ChatGPTConversationsPipe(Pipe[ChatGPTConversationRecord]):
    """ETL pipe for ChatGPT conversations.

    Reads ``conversations.json`` via ijson streaming, yields individual
    :class:`ChatGPTConversationRecord` instances, and transforms each
    into a :class:`ThreadRow` with an ActivityStreams payload.
    """

    provider = "chatgpt"
    interaction_type = "chatgpt_conversations"
    archive_version = "v1"
    archive_path_pattern = "conversations.json"
    record_schema = ChatGPTConversationRecord

    def extract(
        self,
        task: EtlTask,
        storage: StorageBackend,
    ) -> Iterator[ChatGPTConversationRecord]:
        stream = storage.open_stream(task.source_uri)

        try:
            for conversation in ijson.items(stream, "item"):
                conversation_title = conversation.get("title")
                conversation_id = conversation.get("conversation_id")
                mapping = conversation.get("mapping", {})

                for _msg_id, mapping_item in mapping.items():
                    message_data = mapping_item.get("message")
                    if not message_data:
                        continue
                    if "author" not in message_data or "content" not in message_data:
                        continue

                    content = message_data.get("content", {})
                    if content.get("content_type") != "text":
                        continue

                    try:
                        parsed = ChatGPTMessage.model_validate(message_data)
                    except Exception:
                        continue

                    # Skip roles we can't map to a payload
                    if parsed.author.role not in ("user", "assistant"):
                        continue
                    if not parsed.content.parts or not parsed.content.parts[0]:
                        continue
                    text = parsed.content.parts[0]
                    if not text.strip():
                        continue

                    # ijson may return Decimal – coerce for JSON serialization
                    create_time = parsed.create_time
                    if isinstance(create_time, Decimal):
                        create_time = float(create_time)

                    yield ChatGPTConversationRecord(
                        role=parsed.author.role,
                        content=text,
                        create_time=create_time,
                        conversation_id=conversation_id,
                        conversation_title=conversation_title,
                        source=json.dumps(message_data, default=str),
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

        asat = _safe_timestamp(record.create_time) or datetime.now(UTC)

        return ThreadRow(
            unique_key=f"chatgpt_conversations:{payload.unique_key_suffix()}",
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview("ChatGPT") or "",
            payload=payload.to_dict(),
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=asat,
            source=record.source,
        )


INTERACTION_CONFIG = InteractionConfig(
    pipe=ChatGPTConversationsPipe,
    memory=MemoryConfig(
        prompt_builder=ConversationMemoryPromptBuilder,
        grouper=CollectionGrouper,
    ),
)

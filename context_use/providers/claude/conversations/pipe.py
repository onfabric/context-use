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
from context_use.providers.claude.conversations.record import (
    ClaudeConversationRecord,
)
from context_use.providers.claude.conversations.schemas import Model
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)

PROVIDER = "claude"


class ClaudeRole(StrEnum):
    HUMAN = "human"
    ASSISTANT = "assistant"


CLAUDE_APPLICATION = Application(name="assistant")  # type: ignore[reportCallIssue]

_TEXT_BLOCK_TYPE = "text"


def _parse_timestamp(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _build_payload(
    record: ClaudeConversationRecord,
) -> FibreSendMessage | FibreReceiveMessage | None:
    context = None
    if record.conversation_title or record.conversation_id:
        ctx_kwargs: dict = {"type": "Collection"}
        if record.conversation_title:
            ctx_kwargs["name"] = record.conversation_title
        if record.conversation_id:
            ctx_kwargs["id"] = f"https://claude.ai/chat/{record.conversation_id}"
        context = Collection(**ctx_kwargs)

    message = FibreTextMessage(content=record.content, context=context)  # type: ignore[reportCallIssue]

    published = _parse_timestamp(record.created_at)

    if record.role == ClaudeRole.HUMAN:
        return FibreSendMessage(  # type: ignore[reportCallIssue]
            object=message,
            target=CLAUDE_APPLICATION,
            published=published,
        )
    elif record.role == ClaudeRole.ASSISTANT:
        return FibreReceiveMessage(  # type: ignore[reportCallIssue]
            object=message,
            actor=CLAUDE_APPLICATION,
            published=published,
        )

    return None


class ClaudeConversationsPipe(Pipe[ClaudeConversationRecord]):
    provider = PROVIDER
    interaction_type = "claude_conversations"
    archive_version = 1
    archive_path_pattern = "conversations*.json"
    record_schema = ClaudeConversationRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[ClaudeConversationRecord]:
        stream = storage.open_stream(source_uri)

        try:
            for raw_conversation in ijson.items(stream, "item"):
                conversation = Model.model_validate(raw_conversation)

                for message in conversation.chat_messages:
                    if message.sender not in ClaudeRole:
                        continue

                    # The archive stores message text in two places: a top-level
                    # ``text`` field (a pre-rendered composite) and a ``content``
                    # array of typed blocks. For assistant messages that invoked
                    # tools, ``text`` collapses tool_use/tool_result blocks into
                    # "This block is not supported on your current device yet."
                    # placeholders. Extracting only _TEXT_BLOCK_TYPE blocks gives
                    # clean prose without that noise.
                    text = "\n\n".join(
                        block.text
                        for block in message.content
                        if block.type == _TEXT_BLOCK_TYPE
                        and block.text
                        and block.text.strip()
                    )
                    if not text:
                        continue

                    yield ClaudeConversationRecord(
                        role=message.sender,
                        content=text,
                        created_at=message.created_at,
                        conversation_id=conversation.uuid,
                        conversation_title=conversation.name,
                        source=json.dumps(message.model_dump(), default=str),
                    )
        finally:
            stream.close()

    def transform(
        self,
        record: ClaudeConversationRecord,
        task: EtlTask,
    ) -> ThreadRow:
        payload = _build_payload(record)
        assert payload is not None, (
            f"Unexpected None payload for role={record.role!r}; "
            "extract() should have filtered this record"
        )

        asat = _parse_timestamp(record.created_at) or datetime.now(UTC)

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview("Claude") or "",
            payload=payload.to_dict(),
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=asat,
            source=record.source,
            collection_id=payload.get_collection(),
        )


declare_interaction(
    InteractionConfig(
        pipe=ClaudeConversationsPipe,
        memory=MemoryConfig(
            prompt_builder=AgentConversationMemoryPromptBuilder,
            grouper=CollectionGrouper,
        ),
    )
)

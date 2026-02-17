"""ChatGPT conversations extraction + transform strategies."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

import ijson
import pandas as pd

from context_use.core.etl import ExtractionStrategy, TransformStrategy
from context_use.core.types import TaskMetadata
from context_use.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    Application,
    Collection,
    FibreReceiveMessage,
    FibreSendMessage,
    FibreTextMessage,
)
from context_use.providers.chatgpt.schemas import ChatGPTMessage
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)

CHATGPT_APPLICATION = Application(name="assistant")

CHUNK_SIZE = 500

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


# ---------------------------------------------------------------------------
# Extraction – yields DataFrames of raw parsed records
# ---------------------------------------------------------------------------


class ChatGPTConversationsExtractionStrategy(ExtractionStrategy):
    """Reads ``conversations.json``, yields DataFrames of raw message records.

    Each row contains: role, content, create_time, conversation_id,
    conversation_title, content_type.
    """

    def extract(
        self,
        task: TaskMetadata,
        storage: StorageBackend,
    ) -> list[pd.DataFrame]:
        key = task.filenames[0]

        stream = storage.open_stream(key)
        batches: list[pd.DataFrame] = []
        chunk: list[dict] = []

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

                # Skip system messages and empty content
                if parsed.author.role == "system":
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

                chunk.append(
                    {
                        "role": parsed.author.role,
                        "content": text,
                        "create_time": create_time,
                        "conversation_id": conversation_id,
                        "conversation_title": conversation_title,
                        "source": json.dumps(message_data, default=str),
                    }
                )

                if len(chunk) >= CHUNK_SIZE:
                    batches.append(pd.DataFrame(chunk))
                    chunk = []

        if chunk:
            batches.append(pd.DataFrame(chunk))

        stream.close()
        return batches


# ---------------------------------------------------------------------------
# Transform – builds thread-shaped DataFrames
# ---------------------------------------------------------------------------


class ChatGPTConversationsTransformStrategy(TransformStrategy):
    """Transforms raw ChatGPT records into thread-shaped DataFrames with
    ActivityStreams payloads.
    """

    def transform(
        self,
        task: TaskMetadata,
        batches: list[pd.DataFrame],
    ) -> list[pd.DataFrame]:
        result_batches: list[pd.DataFrame] = []

        for df in batches:
            rows: list[dict] = []
            for _, record in df.iterrows():
                payload = self._build_payload(record)
                if payload is None:
                    continue

                create_time = record.get("create_time")
                asat = _safe_timestamp(create_time) or datetime.now(UTC)

                unique_key = f"chatgpt_conversations:{payload.unique_key_suffix()}"
                rows.append(
                    {
                        "unique_key": unique_key,
                        "provider": task.provider,
                        "interaction_type": task.interaction_type,
                        "preview": payload.get_preview("ChatGPT") or "",
                        "payload": payload.to_dict(),
                        "source": record.get("source"),
                        "version": CURRENT_THREAD_PAYLOAD_VERSION,
                        "asat": asat,
                        "asset_uri": None,
                    }
                )

            if rows:
                result_batches.append(pd.DataFrame(rows))

        return result_batches

    @staticmethod
    def _build_payload(
        record: pd.Series,
    ) -> FibreSendMessage | FibreReceiveMessage | None:
        role = record["role"]
        content = record["content"]
        conversation_title = record.get("conversation_title")
        conversation_id = record.get("conversation_id")

        # Build conversation context
        context = None
        if conversation_title or conversation_id:
            ctx_kwargs: dict = {"type": "Collection"}
            if conversation_title:
                ctx_kwargs["name"] = conversation_title
            if conversation_id:
                ctx_kwargs["id"] = f"https://chatgpt.com/c/{conversation_id}"
            context = Collection(**ctx_kwargs)

        message = FibreTextMessage(content=content, context=context)

        create_time = record.get("create_time")
        published = _safe_timestamp(create_time)

        if role == "user":
            return FibreSendMessage(
                object=message,
                target=CHATGPT_APPLICATION,
                published=published,
            )
        elif role == "assistant":
            return FibreReceiveMessage(
                object=message,
                actor=CHATGPT_APPLICATION,
                published=published,
            )

        return None

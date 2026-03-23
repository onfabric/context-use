from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import ijson
from ijson.common import IncompleteJSONError

from context_use.batch.grouper import CollectionGrouper
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    Collection,
    FibreReceiveMessage,
    FibreSendMessage,
    FibreTextMessage,
    Profile,
)
from context_use.memories.config import MemoryConfig
from context_use.memories.prompt.conversation import (
    HumanConversationMemoryPromptBuilder,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.registry import declare_interaction
from context_use.providers.telegram.conversations.record import (
    TelegramConversationRecord,
)
from context_use.providers.telegram.conversations.schemas import Message, Model, Text
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)

PROVIDER = "telegram"

_MESSAGE_TYPE = "message"


def _flatten_text(text: str | list[str | Text]) -> str:
    if isinstance(text, str):
        return text
    parts: list[str] = []
    for part in text:
        if isinstance(part, str):
            parts.append(part)
        else:
            parts.append(part.text)
    return "".join(parts)


def _parse_timestamp(ts_str: str) -> datetime:
    return datetime.fromtimestamp(int(ts_str), tz=UTC)


def _build_payload(
    record: TelegramConversationRecord,
) -> FibreSendMessage | FibreReceiveMessage:
    chat_label = record.chat_name or f"Chat {record.chat_id}"
    ctx_kwargs: dict = {
        "type": "Collection",
        "id": f"https://t.me/c/{record.chat_id}",
        "name": chat_label,
    }
    context = Collection(**ctx_kwargs)
    message = FibreTextMessage(content=record.text, context=context)  # type: ignore[reportCallIssue]
    published = _parse_timestamp(record.date_unixtime)

    if record.is_self:
        return FibreSendMessage(  # type: ignore[reportCallIssue]
            object=message,
            target=Profile(name=chat_label),  # type: ignore[reportCallIssue]
            published=published,
        )
    return FibreReceiveMessage(  # type: ignore[reportCallIssue]
        object=message,
        actor=Profile(name=record.from_name or "Unknown"),  # type: ignore[reportCallIssue]
        published=published,
    )


class TelegramConversationsPipe(Pipe[TelegramConversationRecord]):
    provider = PROVIDER
    interaction_type = "telegram_conversations"
    archive_version = 1
    archive_path_pattern = "result.json"
    record_schema = TelegramConversationRecord

    @staticmethod
    def _read_self_user_id(source_uri: str, storage: StorageBackend) -> str | None:
        stream = storage.open_stream(source_uri)
        try:
            for info in ijson.items(stream, "personal_information"):
                user_id = info.get("user_id")
                if user_id is not None:
                    return f"user{int(user_id)}"
                break
        except (IncompleteJSONError, StopIteration):
            pass
        finally:
            stream.close()
        return None

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[TelegramConversationRecord]:
        self_user_id = self._read_self_user_id(source_uri, storage)

        stream = storage.open_stream(source_uri)
        try:
            for raw_chat in ijson.items(stream, "chats.list.item"):
                chat = Model.model_validate(raw_chat)
                for msg in chat.messages:
                    if msg.type != _MESSAGE_TYPE:
                        continue
                    text = _flatten_text(msg.text)
                    if not text.strip():
                        continue

                    is_self = (
                        msg.from_id == self_user_id
                        if self_user_id and msg.from_id
                        else False
                    )

                    yield TelegramConversationRecord(
                        from_name=msg.from_,
                        from_id=msg.from_id,
                        text=text,
                        date_unixtime=msg.date_unixtime,
                        chat_id=chat.id,
                        chat_name=chat.name,
                        chat_type=chat.type,
                        is_self=is_self,
                        source=_serialize_message(msg),
                    )
        except IncompleteJSONError:
            logger.warning(
                "Incomplete JSON in %s — extracted what was available",
                source_uri,
            )
        finally:
            stream.close()

    def transform(
        self,
        record: TelegramConversationRecord,
        task: EtlTask,
    ) -> ThreadRow:
        payload = _build_payload(record)
        asat = _parse_timestamp(record.date_unixtime)

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview("Telegram") or "",
            payload=payload.to_dict(),
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=asat,
            source=record.source,
            collection_id=payload.get_collection(),
        )


def _serialize_message(msg: Message) -> str:
    return msg.model_dump_json(by_alias=True)


declare_interaction(
    InteractionConfig(
        pipe=TelegramConversationsPipe,
        memory=MemoryConfig(
            prompt_builder=HumanConversationMemoryPromptBuilder,
            grouper=CollectionGrouper,
        ),
    )
)

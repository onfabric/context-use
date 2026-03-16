from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import datetime

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
    HumanConversationMemoryPromptBuilder,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.airbnb.messages.record import AirbnbMessageRecord
from context_use.providers.airbnb.messages.schemas import MessageContent, Model
from context_use.providers.airbnb.schemas import PROVIDER
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)

_AIRBNB_SERVICE = Application(name="Airbnb")  # type: ignore[reportCallIssue]
_AIRBNB_HOST = Application(name="host")  # type: ignore[reportCallIssue]

_OPAQUE_CONTENT_TYPES = frozenset(
    {
        "BulletinContent",
        "CollapsibleActionStackContent",
        "EventDescriptionContent",
        "MediaContent",
        "MsgkitActionCardContent",
        "MsgkitButtonActionStackContent",
        "TranslatedTextContent",
    }
)


def _extract_text(content: MessageContent) -> str | None:
    if content.textContent:
        return content.textContent.body
    if content.messageContentV2:
        return content.messageContentV2.content
    if content.textAndReferenceContent and content.textAndReferenceContent.text:
        return content.textAndReferenceContent.text
    if content.multipleChoiceResponseContent:
        return content.multipleChoiceResponseContent.selectedMultipleChoiceOption.title
    if content.multipleChoicePromptContent:
        return content.multipleChoicePromptContent.promptText
    return None


def _parse_timestamp(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _build_payload(
    record: AirbnbMessageRecord,
) -> FibreSendMessage | FibreReceiveMessage:
    # Airbnb's export does not include the public thread URL; this synthetic
    # URL is constructed from the thread ID for stable collection grouping.
    ctx_kwargs: dict = {
        "type": "Collection",
        "id": f"https://www.airbnb.com/messaging/thread/{record.thread_id}",
    }
    context = Collection(**ctx_kwargs)
    message = FibreTextMessage(content=record.text, context=context)  # type: ignore[reportCallIssue]
    published = _parse_timestamp(record.created_at)

    if record.sender_platform is not None:
        return FibreSendMessage(  # type: ignore[reportCallIssue]
            object=message,
            target=_AIRBNB_SERVICE,
            published=published,
        )
    if record.account_type == "service":
        return FibreReceiveMessage(  # type: ignore[reportCallIssue]
            object=message,
            actor=_AIRBNB_SERVICE,
            published=published,
        )
    return FibreReceiveMessage(  # type: ignore[reportCallIssue]
        object=message,
        actor=_AIRBNB_HOST,
        published=published,
    )


class AirbnbMessagesPipe(Pipe[AirbnbMessageRecord]):
    provider = PROVIDER
    interaction_type = "airbnb_messages"
    archive_version = 1
    archive_path_pattern = "*/json/messages.json"
    record_schema = AirbnbMessageRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[AirbnbMessageRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw_item in ijson.items(stream, "item"):
                item = Model.model_validate(raw_item)
                for thread in item.messageThreads:
                    for mac in thread.messagesAndContents:
                        msg = mac.message
                        if msg.contentType in _OPAQUE_CONTENT_TYPES:
                            continue
                        text = _extract_text(mac.messageContent)
                        if not text:
                            continue
                        yield AirbnbMessageRecord(
                            thread_id=thread.id,
                            message_id=msg.id,
                            created_at=msg.createdAt,
                            account_type=msg.accountType,
                            account_id=msg.accountId,
                            sender_platform=msg.senderPlatform,
                            content_type=msg.contentType,
                            text=text,
                            source=json.dumps(mac.model_dump(), default=str),
                        )
        finally:
            stream.close()

    def transform(
        self,
        record: AirbnbMessageRecord,
        task: EtlTask,
    ) -> ThreadRow:
        payload = _build_payload(record)
        asat = _parse_timestamp(record.created_at)

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview("Airbnb") or "",
            payload=payload.to_dict(),
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=asat,
            source=record.source,
        )


declare_interaction(
    InteractionConfig(
        pipe=AirbnbMessagesPipe,
        memory=MemoryConfig(
            prompt_builder=HumanConversationMemoryPromptBuilder,
            grouper=CollectionGrouper,
        ),
    )
)

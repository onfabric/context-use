from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import ijson

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
from context_use.memories.prompt.conversation import ConversationMemoryPromptBuilder
from context_use.models.etl_task import EtlTask
from context_use.providers.airbnb.schemas import PROVIDER, AirbnbMessageRecord
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)

_AIRBNB_HOST = Profile(name="Host")  # type: ignore[reportCallIssue]


def _extract_text(message_content: dict) -> str | None:
    """Pull the human-readable text from the various content shapes."""
    if tc := message_content.get("textContent"):
        return tc.get("body")
    if trc := message_content.get("textAndReferenceContent"):
        return trc.get("text")
    return None


def _find_owner_account_id(participants: list[dict]) -> int | None:
    """Identify the archive owner among thread participants.

    The owner's participant entry always has ``createdAt`` set (the
    timestamp when they joined/created the thread), while other
    participants typically lack it.  Falls back to the first ``user``
    type participant.
    """
    user_participants = [
        p for p in participants if p.get("accountType") == "user" and p.get("accountId")
    ]
    for p in user_participants:
        if p.get("createdAt"):
            return int(p["accountId"])
    if user_participants:
        return int(user_participants[0]["accountId"])
    return None


class AirbnbMessagesPipe(Pipe[AirbnbMessageRecord]):
    """ETL pipe for Airbnb host/guest messages.

    Streams ``messages.json`` via ijson.  Each top-level item contains
    ``messageThreads``, and each thread contains ``messagesAndContents``.
    System messages (``accountType == "service"`` or no extractable text)
    are filtered during extraction.
    """

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
            for top_level in ijson.items(stream, "item"):
                for thread in top_level.get("messageThreads", []):
                    thread_id = thread.get("id")
                    if thread_id is None:
                        continue

                    participants = thread.get("messageThreadParticipants", [])
                    owner_id = _find_owner_account_id(participants)
                    if owner_id is None:
                        logger.warning(
                            "AirbnbMessagesPipe: cannot determine owner for thread %s",
                            thread_id,
                        )
                        continue

                    for entry in thread.get("messagesAndContents", []):
                        msg = entry.get("message", {})
                        content = entry.get("messageContent", {})

                        if msg.get("accountType") == "service":
                            continue

                        text = _extract_text(content)
                        if not text or not text.strip():
                            continue

                        created_at = msg.get("createdAt")
                        if not created_at:
                            continue

                        yield AirbnbMessageRecord(
                            account_id=msg.get("accountId"),
                            account_type=msg.get("accountType"),
                            text=text.strip(),
                            created_at=created_at,
                            thread_id=int(thread_id),
                            owner_account_id=owner_id,
                            source=json.dumps(entry, default=str),
                        )
        finally:
            stream.close()

    def transform(
        self,
        record: AirbnbMessageRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromisoformat(record.created_at)
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)

        ctx_kwargs: dict = {
            "type": "Collection",
            "id": f"https://www.airbnb.com/messages/thread/{record.thread_id}",
        }
        context = Collection(**ctx_kwargs)
        message = FibreTextMessage(content=record.text, context=context)  # type: ignore[reportCallIssue]

        is_owner = record.account_id == record.owner_account_id

        if is_owner:
            payload = FibreSendMessage(  # type: ignore[reportCallIssue]
                object=message,
                target=_AIRBNB_HOST,
                published=published,
            )
        else:
            payload = FibreReceiveMessage(  # type: ignore[reportCallIssue]
                object=message,
                actor=_AIRBNB_HOST,
                published=published,
            )

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview("Airbnb") or "",
            payload=payload.to_dict(),
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=published,
            source=record.source,
        )


declare_interaction(
    InteractionConfig(
        pipe=AirbnbMessagesPipe,
        memory=MemoryConfig(
            prompt_builder=ConversationMemoryPromptBuilder,
            grouper=CollectionGrouper,
        ),
    )
)

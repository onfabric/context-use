from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime

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
from context_use.providers.instagram.direct_messages.record import (
    InstagramDirectMessageRecord,
)
from context_use.providers.instagram.direct_messages.schemas import (
    InstagramDirectMessageManifest,
)
from context_use.providers.instagram.schemas import PROVIDER
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def _is_attachment_placeholder(content: str) -> bool:
    return content.endswith(" sent an attachment.")


def _link_content_type(link: str) -> str | None:
    if "/stories/" in link:
        return "story"
    if "/reel/" in link:
        return "reel"
    if "/p/" in link:
        return "post"
    return None


def _compose_message_content(record: InstagramDirectMessageRecord) -> str:
    link = record.link or ""
    text = (
        record.content
        if record.content and not _is_attachment_placeholder(record.content)
        else None
    )
    content_type = _link_content_type(link)
    if content_type == "story":
        return f"Replied to story with '{text}'" if text else "Replied to a story"
    if record.original_content_owner and record.share_text:
        snippet = record.share_text[:200].rstrip()
        return f"Shared from @{record.original_content_owner}: {snippet}"
    if record.original_content_owner:
        label = f" ({content_type})" if content_type else ""
        return f"Shared from @{record.original_content_owner}{label}"
    if record.share_text:
        return f"Shared: {record.share_text[:200]}"
    if content_type and text:
        return f"Shared a {content_type} with '{text}'"
    if content_type:
        return f"Shared a {content_type}"
    if text:
        return text
    return link


def _build_payload(
    record: InstagramDirectMessageRecord,
) -> FibreSendMessage | FibreReceiveMessage:
    # The real thread URL (/direct/t/{numeric_id}/) is not present in
    # Instagram's data export. This synthetic URL is a stable unique key
    # for grouping; it does not resolve to an actual conversation.
    ctx_kwargs: dict = {
        "type": "Collection",
        "id": f"https://www.instagram.com/direct/{record.thread_path}",
        "name": record.title,
    }
    context = Collection(**ctx_kwargs)
    msg_kwargs: dict = {"content": _compose_message_content(record), "context": context}
    if record.link:
        msg_kwargs["url"] = record.link
    message = FibreTextMessage(**msg_kwargs)  # type: ignore[reportCallIssue]
    published = datetime.fromtimestamp(record.timestamp_ms / 1000.0, tz=UTC)

    is_inbound = record.sender_name == record.title
    if not is_inbound:
        return FibreSendMessage(  # type: ignore[reportCallIssue]
            object=message,
            target=Profile(name=record.title),  # type: ignore[reportCallIssue]
            published=published,
        )
    return FibreReceiveMessage(  # type: ignore[reportCallIssue]
        object=message,
        actor=Profile(name=record.sender_name),  # type: ignore[reportCallIssue]
        published=published,
    )


class _InstagramDMPipe(Pipe[InstagramDirectMessageRecord]):
    provider = PROVIDER
    archive_version = 1
    record_schema = InstagramDirectMessageRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramDirectMessageRecord]:
        raw = storage.read(source_uri)
        manifest = InstagramDirectMessageManifest.model_validate_json(raw)

        for msg in manifest.messages:
            share = msg.share
            link = share.link if share else None
            share_text = share.share_text if share else None
            original_content_owner = share.original_content_owner if share else None

            if not msg.content and not link and not share_text:
                continue

            yield InstagramDirectMessageRecord(
                sender_name=msg.sender_name,
                content=msg.content,
                link=link,
                share_text=share_text,
                original_content_owner=original_content_owner,
                timestamp_ms=msg.timestamp_ms,
                thread_path=manifest.thread_path,
                title=manifest.title,
                source=msg.model_dump_json(),
            )

    def transform(
        self,
        record: InstagramDirectMessageRecord,
        task: EtlTask,
    ) -> ThreadRow:
        payload = _build_payload(record)
        asat = datetime.fromtimestamp(record.timestamp_ms / 1000.0, tz=UTC)

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview("Instagram") or "",
            payload=payload.to_dict(),
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=asat,
            source=record.source,
            collection_id=payload.get_collection(),
        )


class InstagramDirectMessagesPipe(_InstagramDMPipe):
    interaction_type = "instagram_direct_messages"
    archive_path_pattern = "your_instagram_activity/messages/inbox/*/message_*.json"


declare_interaction(
    InteractionConfig(
        pipe=InstagramDirectMessagesPipe,
        memory=MemoryConfig(
            prompt_builder=HumanConversationMemoryPromptBuilder,
            grouper=CollectionGrouper,
        ),
    )
)

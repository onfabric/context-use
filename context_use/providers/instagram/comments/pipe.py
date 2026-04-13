from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import ijson

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreComment,
    FibrePost,
    Note,
    Profile,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.comments.record import InstagramCommentRecord
from context_use.providers.instagram.comments.schemas import (
    InstagramCommentFileItem,
    InstagramReelsCommentsManifest,
)
from context_use.providers.instagram.schemas import PROVIDER
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class _InstagramCommentPipe(Pipe[InstagramCommentRecord]):
    """Shared transform logic for Instagram comment pipes.

    Subclasses set :attr:`interaction_type`, :attr:`archive_path_pattern`,
    and optionally :attr:`_json_key` for keyed JSON files.
    """

    provider = PROVIDER
    archive_version = 1
    record_schema = InstagramCommentRecord

    @staticmethod
    def _extract_item(
        item: InstagramCommentFileItem,
    ) -> InstagramCommentRecord | None:
        smd = item.string_map_data
        comment_val = smd.Comment.value if smd.Comment else None
        media_url: str | None = None
        if not comment_val:
            if item.media_list_data:
                media_url = item.media_list_data[0].uri
                comment_val = "[GIF]"
            else:
                return None
        media_owner = smd.Media_Owner.value if smd.Media_Owner else None
        return InstagramCommentRecord(
            comment=comment_val,
            media_owner=media_owner,
            media_url=media_url,
            timestamp=smd.Time.timestamp,
            source=item.model_dump_json(),
        )

    def transform(
        self,
        record: InstagramCommentRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)

        note = Note(content=record.comment, url=record.media_url, published=published)  # type: ignore[reportCallIssue]

        in_reply_to: FibrePost | None = None
        if record.media_owner:
            in_reply_to = FibrePost(  # type: ignore[reportCallIssue]
                attributedTo=Profile(name=record.media_owner),  # type: ignore[reportCallIssue]
            )

        payload = FibreComment(  # type: ignore[reportCallIssue]
            object=note,
            inReplyTo=in_reply_to,
            published=published,
        )

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview(task.provider) or "",
            payload=payload.to_dict(),
            source=record.source,
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=published,
        )


class InstagramCommentPostsPipe(_InstagramCommentPipe):
    interaction_type = "instagram_comments_posts"
    archive_path_pattern = "your_instagram_activity/comments/post_comments*.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramCommentRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for item in self._validated_items(
                ijson.items(stream, "item"), InstagramCommentFileItem
            ):
                record = self._extract_item(item)
                if record is not None:
                    yield record
        finally:
            stream.close()


class InstagramCommentReelsPipe(_InstagramCommentPipe):
    interaction_type = "instagram_comments_reels"
    archive_path_pattern = "your_instagram_activity/comments/reels_comments.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramCommentRecord]:
        raw = storage.read(source_uri)
        manifest = InstagramReelsCommentsManifest.model_validate_json(raw)
        for item in manifest.comments_reels_comments:
            record = self._extract_item(item)
            if record is not None:
                yield record


declare_interaction(InteractionConfig(pipe=InstagramCommentPostsPipe, memory=None))
declare_interaction(InteractionConfig(pipe=InstagramCommentReelsPipe, memory=None))

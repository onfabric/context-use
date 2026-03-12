from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import ClassVar

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
from context_use.providers.instagram.schemas import (
    PROVIDER,
    InstagramCommentRecord,
)
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

    _json_key: ClassVar[str | None] = None
    """Top-level JSON key wrapping the items array, or ``None`` for bare arrays."""

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramCommentRecord]:
        raw = storage.read(source_uri)
        data = json.loads(raw)

        items = data.get(self._json_key, []) if self._json_key is not None else data
        for raw_item in items:
            smd = raw_item.get("string_map_data", {})

            comment_val = smd.get("Comment", {}).get("value")
            if not comment_val:
                continue

            media_owner = smd.get("Media Owner", {}).get("value")
            timestamp_val = smd.get("Time", {}).get("timestamp")
            if timestamp_val is None:
                continue

            yield InstagramCommentRecord(
                comment=comment_val,
                media_owner=media_owner,
                timestamp=timestamp_val,
                source=json.dumps(raw_item),
            )

    def transform(
        self,
        record: InstagramCommentRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)

        note = Note(content=record.comment, published=published)  # type: ignore[reportCallIssue]

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
    """ETL pipe for Instagram post comments.

    Reads a bare top-level JSON array from
    ``your_instagram_activity/comments/post_comments_1.json``.
    Each item has ``{string_map_data: {Comment, "Media Owner", Time}}``.
    """

    interaction_type = "instagram_comments_posts"
    archive_path_pattern = "your_instagram_activity/comments/post_comments*.json"
    _json_key = None


class InstagramCommentReelsPipe(_InstagramCommentPipe):
    """ETL pipe for Instagram reel comments.

    Reads ``comments_reels_comments`` from
    ``your_instagram_activity/comments/reels_comments.json``.
    Each item has ``{string_map_data: {Comment, "Media Owner", Time}}``.
    """

    interaction_type = "instagram_comments_reels"
    archive_path_pattern = "your_instagram_activity/comments/reels_comments.json"
    _json_key = "comments_reels_comments"


declare_interaction(InteractionConfig(pipe=InstagramCommentPostsPipe, memory=None))
declare_interaction(InteractionConfig(pipe=InstagramCommentReelsPipe, memory=None))

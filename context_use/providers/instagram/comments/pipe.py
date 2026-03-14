from __future__ import annotations

import json
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
from context_use.providers.instagram.comments.schemas_post_comments import (
    Model as PostCommentItem,
)
from context_use.providers.instagram.comments.schemas_reels_comments import (
    Model as ReelsCommentsManifest,
)
from context_use.providers.instagram.schemas import PROVIDER, _fix_strings_recursive
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class _InstagramCommentPipe(Pipe[InstagramCommentRecord]):
    provider = PROVIDER
    archive_version = 1
    record_schema = InstagramCommentRecord

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
    interaction_type = "instagram_comments_posts"
    archive_path_pattern = "your_instagram_activity/comments/post_comments*.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramCommentRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                item = PostCommentItem.model_validate(_fix_strings_recursive(raw))
                smd = item.string_map_data
                comment_val = smd.Comment_1.value
                if not comment_val:
                    continue
                media_owner = smd.Media_Owner.value if smd.Media_Owner else None
                yield InstagramCommentRecord(
                    comment=comment_val,
                    media_owner=media_owner,
                    timestamp=smd.Time_1.timestamp,
                    source=item.model_dump_json(),
                )
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
        data = _fix_strings_recursive(json.loads(raw))
        manifest = ReelsCommentsManifest.model_validate(data)
        for item in manifest.comments_reels_comments:
            smd = item.string_map_data
            comment_val = smd.Comment_1.value
            if not comment_val:
                continue
            media_owner = smd.Media_Owner.value if smd.Media_Owner else None
            yield InstagramCommentRecord(
                comment=comment_val,
                media_owner=media_owner,
                timestamp=smd.Time_1.timestamp,
                source=item.model_dump_json(),
            )


declare_interaction(InteractionConfig(pipe=InstagramCommentPostsPipe, memory=None))
declare_interaction(InteractionConfig(pipe=InstagramCommentReelsPipe, memory=None))

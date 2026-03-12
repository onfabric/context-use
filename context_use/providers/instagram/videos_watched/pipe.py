from __future__ import annotations

from datetime import UTC, datetime

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreViewObject,
    Profile,
    Video,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.schemas import PROVIDER
from context_use.providers.instagram.videos_watched.record import (
    InstagramVideoWatchedRecord,
)


class _InstagramVideosWatchedPipe(Pipe[InstagramVideoWatchedRecord]):
    provider = PROVIDER
    interaction_type = "instagram_videos_watched"
    record_schema = InstagramVideoWatchedRecord

    def transform(
        self,
        record: InstagramVideoWatchedRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)

        video_kwargs: dict = {}
        if record.video_url:
            video_kwargs["url"] = record.video_url
        if record.author:
            video_kwargs["attributedTo"] = Profile(  # type: ignore[reportCallIssue]
                name=record.author,
                url=f"https://www.instagram.com/{record.author}",
            )

        video = Video(**video_kwargs)  # type: ignore[reportCallIssue]

        payload = FibreViewObject(  # type: ignore[reportCallIssue]
            object=video,
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

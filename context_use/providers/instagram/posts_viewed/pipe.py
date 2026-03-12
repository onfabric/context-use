from __future__ import annotations

from datetime import UTC, datetime

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibrePost,
    FibreViewObject,
    Profile,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.posts_viewed.record import (
    InstagramPostsViewedRecord,
)
from context_use.providers.instagram.schemas import PROVIDER


class InstagramPostsViewedPipe(Pipe[InstagramPostsViewedRecord]):
    provider = PROVIDER
    interaction_type = "instagram_posts_viewed"
    record_schema = InstagramPostsViewedRecord

    def transform(
        self,
        record: InstagramPostsViewedRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)

        post_kwargs: dict = {}
        if record.post_url:
            post_kwargs["url"] = record.post_url
        if record.author:
            post_kwargs["attributedTo"] = Profile(  # type: ignore[reportCallIssue]
                name=record.author,
                url=f"https://www.instagram.com/{record.author}",
            )

        post = FibrePost(**post_kwargs)  # type: ignore[reportCallIssue]

        payload = FibreViewObject(  # type: ignore[reportCallIssue]
            object=post,
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

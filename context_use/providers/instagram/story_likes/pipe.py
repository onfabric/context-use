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
    FibreLike,
    FibrePost,
    Profile,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.schemas import (
    PROVIDER,
    _fix_strings_recursive,
)
from context_use.providers.instagram.story_likes.record import InstagramStoryLikeRecord
from context_use.providers.instagram.story_likes.schemas import (
    LabelValue,
    Model,
)
from context_use.providers.instagram.story_likes.schemas_v0 import (
    Model as V0Model,
)
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def _ts_to_datetime(ts: int) -> datetime:
    return datetime.fromtimestamp(float(ts), tz=UTC)


def _extract_v1_owner_username(lv: LabelValue) -> str | None:
    if lv.dict_ is None:
        return None
    for group in lv.dict_:
        for entry in group.dict_:
            if entry.label == "Username":
                return entry.value
    return None


class _InstagramStoryLikePipe(Pipe[InstagramStoryLikeRecord]):
    provider = PROVIDER
    record_schema = InstagramStoryLikeRecord
    interaction_type = "instagram_story_likes"

    def transform(
        self,
        record: InstagramStoryLikeRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = _ts_to_datetime(record.timestamp)

        post_kwargs: dict = {}
        if record.href:
            post_kwargs["url"] = record.href
        if record.title:
            post_kwargs["attributedTo"] = Profile(  # type: ignore[reportCallIssue]
                name=record.title,
            )

        post = FibrePost(**post_kwargs)  # type: ignore[reportCallIssue]

        payload = FibreLike(  # type: ignore[reportCallIssue]
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


class InstagramStoryLikesV0Pipe(_InstagramStoryLikePipe):
    archive_version = 0
    archive_path_pattern = "your_instagram_activity/story_interactions/story_likes.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramStoryLikeRecord]:
        raw = storage.read(source_uri)
        data = _fix_strings_recursive(json.loads(raw))
        manifest = V0Model.model_validate(data)
        for item in manifest.story_activities_story_likes:
            item_json = item.model_dump_json()
            for entry in item.string_list_data:
                yield InstagramStoryLikeRecord(
                    title=item.title,
                    href=None,
                    timestamp=entry.timestamp,
                    source=item_json,
                )


class InstagramStoryLikesPipe(_InstagramStoryLikePipe):
    archive_version = 1
    archive_path_pattern = "your_instagram_activity/story_interactions/story_likes.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramStoryLikeRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                fixed = _fix_strings_recursive(raw)
                item = Model.model_validate(fixed)
                href: str | None = None
                title: str | None = None

                for lv in item.label_values:
                    if lv.label == "URL":
                        href = lv.href or lv.value
                    elif lv.dict_ is not None and lv.title == "Owner":
                        title = _extract_v1_owner_username(lv)

                yield InstagramStoryLikeRecord(
                    title=title or "",
                    href=href,
                    timestamp=item.timestamp,
                    source=json.dumps(fixed),
                )
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=InstagramStoryLikesPipe, memory=None))

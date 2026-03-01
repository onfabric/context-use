from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import ClassVar

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreFollow,
    Profile,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.schemas import (
    InstagramConnectionItem,
    InstagramConnectionRecord,
    InstagramFollowingManifest,
)
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend


def _parse_connection_item(raw_item: dict) -> InstagramConnectionRecord:
    """Validate a raw archive dict and flatten into a connection record."""
    item = InstagramConnectionItem.model_validate(raw_item)
    sld = item.string_list_data[0]
    username = sld.href.rstrip("/").split("/")[-1]
    return InstagramConnectionRecord(
        username=username,
        profile_url=sld.href,
        timestamp=sld.timestamp,
        source=json.dumps(raw_item),
    )


class _InstagramConnectionPipe(Pipe[InstagramConnectionRecord]):
    """Shared transform logic for Instagram follower/following pipes.

    Subclasses set :attr:`interaction_type`, :attr:`archive_path_pattern`,
    and :attr:`_is_inbound` then implement :meth:`extract_file`.
    """

    provider = "instagram"
    archive_version = 1
    record_schema = InstagramConnectionRecord

    _is_inbound: ClassVar[bool] = False

    def transform(
        self,
        record: InstagramConnectionRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)
        profile = Profile(  # type: ignore[reportCallIssue]
            name=record.username,
            url=record.profile_url,
        )

        if self._is_inbound:
            payload = FibreFollow(actor=profile, published=published)  # type: ignore[reportCallIssue]
        else:
            payload = FibreFollow(object=profile, published=published)  # type: ignore[reportCallIssue]

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


class InstagramFollowersPipe(_InstagramConnectionPipe):
    """ETL pipe for Instagram followers.

    Reads ``followers_*.json`` (top-level JSON array of connection items)
    and transforms each into a :class:`ThreadRow` with an inbound
    :class:`FibreFollow` payload.
    """

    interaction_type = "instagram_followers"
    archive_path_pattern = "connections/followers_and_following/followers_*.json"
    _is_inbound = True

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramConnectionRecord]:
        raw = storage.read(source_uri)
        items: list[dict] = json.loads(raw)
        for item_dict in items:
            yield _parse_connection_item(item_dict)


class InstagramFollowingPipe(_InstagramConnectionPipe):
    """ETL pipe for Instagram following.

    Reads ``following.json`` (keyed under ``relationships_following``)
    and transforms each into a :class:`ThreadRow` with an outbound
    :class:`FibreFollow` payload.
    """

    interaction_type = "instagram_following"
    archive_path_pattern = "connections/followers_and_following/following.json"
    _is_inbound = False

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramConnectionRecord]:
        raw = storage.read(source_uri)
        manifest = InstagramFollowingManifest.model_validate_json(raw)
        for item in manifest.relationships_following:
            sld = item.string_list_data[0]
            username = sld.href.rstrip("/").split("/")[-1]
            yield InstagramConnectionRecord(
                username=username,
                profile_url=sld.href,
                timestamp=sld.timestamp,
                source=item.model_dump_json(),
            )


FOLLOWERS_CONFIG = InteractionConfig(
    pipe=InstagramFollowersPipe,
    memory=None,
)

FOLLOWING_CONFIG = InteractionConfig(
    pipe=InstagramFollowingPipe,
    memory=None,
)

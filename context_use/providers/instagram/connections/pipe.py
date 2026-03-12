from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import ClassVar

import ijson

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreFollowedBy,
    FibreFollowing,
    Person,
    Profile,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.instagram.connections.record import (
    InstagramConnectionRecord,
)
from context_use.providers.instagram.connections.schemas import (
    InstagramConnectionItem,
    InstagramFollowingManifest,
)
from context_use.providers.instagram.schemas import PROVIDER
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def _parse_connection_item(item: InstagramConnectionItem) -> InstagramConnectionRecord:
    sld = item.string_list_data[0]
    username = (
        (sld.href or "").rstrip("/").split("/")[-1] if sld.href else (sld.value or "")
    )
    return InstagramConnectionRecord(
        username=username,
        profile_url=sld.href,
        timestamp=sld.timestamp,
        source=item.model_dump_json(),
    )


class _InstagramConnectionPipe(Pipe[InstagramConnectionRecord]):
    """Shared transform logic for Instagram follower/following pipes.

    Subclasses set :attr:`interaction_type`, :attr:`archive_path_pattern`,
    and :attr:`_is_inbound` then implement :meth:`extract_file`.
    """

    provider = PROVIDER
    archive_version = 1
    record_schema = InstagramConnectionRecord

    _is_inbound: ClassVar[bool] = False

    def transform(
        self,
        record: InstagramConnectionRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = datetime.fromtimestamp(float(record.timestamp), tz=UTC)

        if self._is_inbound:
            # FibreFollowedBy.actor is Person (not Profile)
            actor = Person(  # type: ignore[reportCallIssue]
                name=record.username,
                url=record.profile_url,
            )
            payload = FibreFollowedBy(  # type: ignore[reportCallIssue]
                actor=actor,
                published=published,
            )
        else:
            profile = Profile(  # type: ignore[reportCallIssue]
                name=record.username,
                url=record.profile_url,
            )
            payload = FibreFollowing(  # type: ignore[reportCallIssue]
                object=profile,
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


class InstagramFollowersPipe(_InstagramConnectionPipe):
    """ETL pipe for Instagram followers.

    Reads ``followers_*.json`` (top-level JSON array of connection items)
    and transforms each into a :class:`ThreadRow` with an inbound
    :class:`FibreFollowedBy` payload.
    """

    interaction_type = "instagram_followers"
    archive_path_pattern = "connections/followers_and_following/followers_*.json"
    _is_inbound = True

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramConnectionRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                item = InstagramConnectionItem.model_validate(raw)
                yield _parse_connection_item(item)
        finally:
            stream.close()


class InstagramFollowingPipe(_InstagramConnectionPipe):
    """ETL pipe for Instagram following.

    Reads ``following.json`` (keyed under ``relationships_following``)
    and transforms each into a :class:`ThreadRow` with an outbound
    :class:`FibreFollowing` payload.
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
            # Use title as username; fall back to extracting from href
            username = item.title or (
                sld.href.rstrip("/").split("/")[-1] if sld.href else ""
            )
            yield InstagramConnectionRecord(
                username=username,
                profile_url=sld.href,
                timestamp=sld.timestamp,
                source=item.model_dump_json(),
            )


declare_interaction(InteractionConfig(pipe=InstagramFollowersPipe, memory=None))
declare_interaction(InteractionConfig(pipe=InstagramFollowingPipe, memory=None))

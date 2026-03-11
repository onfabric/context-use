from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property
from typing import TYPE_CHECKING

from context_use.models.utils import generate_uuidv4

if TYPE_CHECKING:
    from context_use.etl.payload.models import ThreadPayload


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Thread:
    """A single normalised interaction thread.

    Carries all domain fields and business methods.  Infrastructure
    fields (``created_at``, ``updated_at``) have sensible defaults so
    the model works both in-memory and when hydrated from a database.
    """

    unique_key: str
    provider: str
    interaction_type: str
    preview: str
    payload: dict
    version: str
    asat: datetime

    id: str = field(default_factory=generate_uuidv4)
    etl_task_id: str | None = None
    asset_uri: str | None = None
    source: str | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    @cached_property
    def _parsed_payload(self) -> ThreadPayload:
        from context_use.etl.payload.core import make_thread_payload

        return make_thread_payload(self.payload)

    @property
    def is_asset(self) -> bool:
        return self.asset_uri is not None

    @property
    def is_inbound(self) -> bool:
        """Whether this thread was performed by someone else toward the user."""
        return self._parsed_payload.is_inbound()

    def get_message_content(self) -> str | None:
        """Get the text content of a message thread (None for non-message threads)."""
        return self._parsed_payload.get_message_content()

    def get_collection(self) -> str | None:
        """Get collection ID for this thread."""
        return self._parsed_payload.get_collection()

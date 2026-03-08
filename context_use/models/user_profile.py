from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class UserProfile:
    """A single, updatable user profile document.

    There is exactly one profile per store.  The ``content`` field holds
    the full Markdown profile compiled by the agent.
    """

    content: str
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

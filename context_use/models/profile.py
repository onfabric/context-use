from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from context_use.models.utils import generate_uuidv4


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class TapestryProfile:
    """A user profile distilled from memories."""

    content: str
    generated_at: datetime
    memory_count: int

    id: str = field(default_factory=generate_uuidv4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

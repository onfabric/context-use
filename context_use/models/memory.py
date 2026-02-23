from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from context_use.models.utils import generate_uuidv4


def _utcnow() -> datetime:
    return datetime.now(UTC)


EMBEDDING_DIMENSIONS = 3072


class MemoryStatus(enum.StrEnum):
    active = "active"
    superseded = "superseded"


@dataclass
class TapestryMemory:
    """A single memory covering a date range."""

    content: str
    from_date: date
    to_date: date
    group_id: str

    id: str = field(default_factory=generate_uuidv4)
    embedding: list[float] | None = None
    status: str = MemoryStatus.active.value
    superseded_by: str | None = None
    source_memory_ids: list[str] | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from context_use.models.utils import generate_uuidv4


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class MemoryFacet:
    memory_id: str
    facet_type: str
    facet_value: str
    id: str = field(default_factory=generate_uuidv4)
    batch_id: str | None = None
    facet_id: str | None = None
    embedding: list[float] | None = None
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class Facet:
    facet_type: str
    facet_canonical: str
    id: str = field(default_factory=generate_uuidv4)
    created_at: datetime = field(default_factory=_utcnow)

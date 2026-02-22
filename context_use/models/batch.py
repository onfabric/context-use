from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class BatchCategory(enum.StrEnum):
    """Extensible registry of pipeline categories."""

    memories = "memories"
    refinement = "refinement"


@dataclass
class Batch:
    """A batch of thread groups to be processed by a pipeline."""

    batch_number: int
    category: str
    states: list[dict]

    id: str = field(default_factory=_new_id)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass
class BatchThread:
    """Mapping of a thread to a batch, identified by group_id."""

    batch_id: str
    thread_id: str
    group_id: str

    id: str = field(default_factory=_new_id)

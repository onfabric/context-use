from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime

from context_use.models.utils import generate_uuidv4


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ArchiveStatus(enum.StrEnum):
    CREATED = "created"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Archive:
    """An uploaded provider archive (zip file)."""

    provider: str

    id: str = field(default_factory=generate_uuidv4)
    status: str = ArchiveStatus.CREATED.value
    file_uris: list[str] | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

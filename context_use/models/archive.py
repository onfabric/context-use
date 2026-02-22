from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class ArchiveStatus(enum.StrEnum):
    CREATED = "created"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Archive:
    """An uploaded provider archive (zip file)."""

    provider: str

    id: str = field(default_factory=_new_id)
    status: str = ArchiveStatus.CREATED.value
    file_uris: list[str] | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

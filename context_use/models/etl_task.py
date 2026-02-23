from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime

from context_use.models.utils import generate_id


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EtlTaskStatus(enum.StrEnum):
    CREATED = "created"
    EXTRACTING = "extracting"
    TRANSFORMING = "transforming"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class EtlTask:
    """A single ETL task within an archive."""

    archive_id: str
    provider: str
    interaction_type: str
    source_uri: str

    id: str = field(default_factory=generate_id)
    status: str = EtlTaskStatus.CREATED.value
    extracted_count: int = 0
    transformed_count: int = 0
    uploaded_count: int = 0
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

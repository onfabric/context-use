from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel


@dataclass
class ExtractedBatch[T: BaseModel]:
    """Typed batch of records flowing from Extract to Transform."""

    records: list[T]

    def __len__(self) -> int:
        return len(self.records)


@dataclass
class ThreadRow:
    """Plain value object flowing from Pipe.transform() to Loader.load().

    Contains only the domain data needed to represent a thread.
    Infrastructure concerns (``id``, ``tapestry_id``, ``etl_task_id``,
    timestamps) are added by the Loader when persisting.
    """

    unique_key: str
    provider: str
    interaction_type: str
    preview: str
    payload: dict
    version: str
    asat: datetime
    source: str | None = None
    asset_uri: str | None = None


@dataclass
class PipelineResult:
    """Result returned from process_archive()."""

    archive_id: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    threads_created: int = 0
    errors: list[str] = field(default_factory=list)

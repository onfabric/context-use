from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass
class ExtractedBatch[T: BaseModel]:
    """Typed batch of records flowing from Extract to Transform."""

    records: list[T]

    def __len__(self) -> int:
        return len(self.records)


@dataclass
class PipelineResult:
    """Result returned from process_archive()."""

    archive_id: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    threads_created: int = 0
    errors: list[str] = field(default_factory=list)

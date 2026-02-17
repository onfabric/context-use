"""ETL task metadata types."""

from __future__ import annotations

from dataclasses import dataclass, asdict, field, fields as dataclass_fields
from typing import Any


@dataclass
class TaskMetadata:
    """Metadata passed through every ETL pipeline step."""

    archive_id: str
    etl_task_id: str
    provider: str
    interaction_type: str
    filenames: list[str] = field(default_factory=list)
    tapestry_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskMetadata:
        known = {f.name for f in dataclass_fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class PipelineResult:
    """Result returned from process_archive()."""

    archive_id: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    threads_created: int = 0
    errors: list[str] = field(default_factory=list)


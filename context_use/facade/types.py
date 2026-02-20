"""Public return types for the context_use API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class PipelineResult:
    """Result from :meth:`ContextUse.process_archive`."""

    archive_id: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    threads_created: int = 0
    errors: list[str] = field(default_factory=list)
    breakdown: list[TaskBreakdown] = field(default_factory=list)


@dataclass
class TaskBreakdown:
    """Per-interaction-type stats included in :class:`PipelineResult`."""

    interaction_type: str
    thread_count: int


@dataclass
class MemoriesResult:
    """Result from :meth:`ContextUse.generate_memories`."""

    tasks_processed: int = 0
    batches_created: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class RefinementResult:
    """Result from :meth:`ContextUse.refine_memories`."""

    batches_created: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ArchiveSummary:
    """Summary of a completed archive."""

    id: str
    provider: str
    created_at: datetime
    thread_count: int


@dataclass
class MemorySummary:
    """Public representation of a single memory."""

    id: str
    content: str
    from_date: date
    to_date: date


@dataclass
class ProfileSummary:
    """Public representation of a generated profile."""

    content: str
    generated_at: datetime
    memory_count: int

from __future__ import annotations

from dataclasses import dataclass, field


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

    task_id: str
    interaction_type: str
    thread_count: int

"""Public API for the context_use library.

External consumers (CLI, MCP server, etc.) should import exclusively
from this module.  Only unit / integration tests may reach into
sub-packages directly.
"""

import context_use.providers  # noqa: F401 — triggers provider registration
from context_use.facade import (
    ContextUse,
    MemorySummary,
    PipelineResult,
    ScheduleInstruction,
    TaskBreakdown,
)
from context_use.store import InMemoryStore, Store

__all__ = [
    "ContextUse",
    "InMemoryStore",
    "MemorySummary",
    "PipelineResult",
    "ScheduleInstruction",
    "Store",
    "TaskBreakdown",
]

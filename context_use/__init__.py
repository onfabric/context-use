"""Public API for the context_use library.

External consumers (CLI, MCP server, etc.) should import exclusively
from this module.  Only unit / integration tests may reach into
sub-packages directly.
"""

from context_use.facade import (
    ArchiveSummary,
    ContextUse,
    MemoriesResult,
    MemorySummary,
    PipelineResult,
    ProfileSummary,
    RefinementResult,
    TaskBreakdown,
)
from context_use.providers.registry import Provider

__all__ = [
    "ArchiveSummary",
    "ContextUse",
    "MemoriesResult",
    "MemorySummary",
    "PipelineResult",
    "ProfileSummary",
    "Provider",
    "RefinementResult",
    "TaskBreakdown",
]

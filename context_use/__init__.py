"""Public API for the context_use library.

External consumers (CLI, agent, etc.) should import exclusively
from this module.  Only unit / integration tests may reach into
sub-packages directly.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from context_use.facade import (
        ContextUse,
        PipelineResult,
        ScheduleInstruction,
        TaskBreakdown,
    )
    from context_use.store import SqliteStore, Store

__all__ = [
    "ContextUse",
    "PipelineResult",
    "ScheduleInstruction",
    "SqliteStore",
    "Store",
    "TaskBreakdown",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    import_module("context_use.providers")
    from context_use.facade import (
        ContextUse,
        PipelineResult,
        ScheduleInstruction,
        TaskBreakdown,
    )
    from context_use.store import SqliteStore, Store

    exports = {
        "ContextUse": ContextUse,
        "PipelineResult": PipelineResult,
        "ScheduleInstruction": ScheduleInstruction,
        "SqliteStore": SqliteStore,
        "Store": Store,
        "TaskBreakdown": TaskBreakdown,
    }
    value = exports[name]
    globals()[name] = value
    return value

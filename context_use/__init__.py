"""Public API for the context_use library.

External consumers (CLI, agent, etc.) should import exclusively
from this module.  Only unit / integration tests may reach into
sub-packages directly.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from context_use.facade import (
        ContextUse,
        PipelineResult,
        ScheduleInstruction,
        TaskBreakdown,
    )
    from context_use.proxy.handler import (
        ContextProxy,
        ContextProxyResult,
        ContextProxyStreamResult,
    )
    from context_use.proxy.app import create_proxy_app
    from context_use.store import SqliteStore, Store

__all__ = [
    "ContextProxy",
    "ContextProxyResult",
    "ContextProxyStreamResult",
    "ContextUse",
    "PipelineResult",
    "ScheduleInstruction",
    "SqliteStore",
    "Store",
    "TaskBreakdown",
    "create_proxy_app",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from context_use.facade import (
        ContextUse,
        PipelineResult,
        ScheduleInstruction,
        TaskBreakdown,
    )
    from context_use.proxy.handler import (
        ContextProxy,
        ContextProxyResult,
        ContextProxyStreamResult,
    )
    from context_use.proxy.app import create_proxy_app
    from context_use.store import SqliteStore, Store

    exports: dict[str, Any] = {
        "ContextProxy": ContextProxy,
        "ContextProxyResult": ContextProxyResult,
        "ContextProxyStreamResult": ContextProxyStreamResult,
        "ContextUse": ContextUse,
        "PipelineResult": PipelineResult,
        "ScheduleInstruction": ScheduleInstruction,
        "SqliteStore": SqliteStore,
        "Store": Store,
        "TaskBreakdown": TaskBreakdown,
        "create_proxy_app": create_proxy_app,
    }

    value = exports[name]
    globals()[name] = value
    return value

from __future__ import annotations

from abc import ABC, abstractmethod

from context_use.db.models import new_uuid


class RunPolicy(ABC):
    """Controls when and whether a pipeline run should proceed."""

    @abstractmethod
    async def acquire(self) -> str | None:
        """Try to start a run.

        Returns a ``run_id`` if the run is allowed, ``None`` if rejected
        (e.g. another run is already active).
        """
        ...

    @abstractmethod
    async def release(self, run_id: str, *, success: bool) -> None:
        """Mark a run as finished (successfully or not)."""
        ...


class ImmediateRunPolicy(RunPolicy):
    """Always allow. No locking, no tracking."""

    async def acquire(self) -> str | None:
        return new_uuid()

    async def release(self, run_id: str, *, success: bool) -> None:
        pass

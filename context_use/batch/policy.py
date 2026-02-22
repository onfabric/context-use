from __future__ import annotations

import uuid
from abc import ABC, abstractmethod


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
        return str(uuid.uuid4())

    async def release(self, run_id: str, *, success: bool) -> None:
        pass

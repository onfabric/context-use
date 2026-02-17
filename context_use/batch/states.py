"""Base state classes for the batch state machine.

Portable: this file is identical between context-use and aertex.
The state hierarchy controls how the runner (async loop or Celery)
decides what to do after each transition.

Hierarchy:
    State (ABC)
    ├── CurrentState   → runner waits ``poll_next_countdown`` seconds, then re-advances
    ├── NextState      → runner re-advances immediately
    ├── RetryState     → runner waits ``retry_countdown`` seconds, then re-advances
    └── StopState      → runner stops (terminal)
"""

from __future__ import annotations

from abc import abstractmethod
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Abstract state bases
# ---------------------------------------------------------------------------


class State:
    """Base marker for all states."""


class CurrentState(State):
    """Polling state — the runner should wait then re-check.

    Subclasses MUST define ``poll_next_countdown`` and include
    a ``poll_count: int = 0`` field.
    """

    poll_count: int = 0

    @property
    @abstractmethod
    def poll_next_countdown(self) -> int:
        """Seconds to wait before the next poll."""

    def increment_poll_count(self) -> CurrentState:
        return self.__class__(
            **{**self.model_dump(), "poll_count": self.poll_count + 1}
        )


class NextState(State):
    """Transition state — the runner should advance immediately."""


class RetryState(State):
    """Retry state — the runner should wait then retry the same step.

    Subclasses MUST define ``retry_countdown`` and include
    a ``retry_count: int = 0`` field.
    """

    retry_count: int = 0

    @property
    @abstractmethod
    def retry_countdown(self) -> int:
        """Seconds to wait before retrying."""

    def increment_retry_count(self) -> RetryState:
        return self.__class__(
            **{**self.model_dump(), "retry_count": self.retry_count + 1}
        )


class StopState:
    """Terminal state — the runner does not reschedule."""


# ---------------------------------------------------------------------------
# Shared concrete states (used by every pipeline)
# ---------------------------------------------------------------------------


class CreatedState(BaseModel, NextState):
    """Batch created — ready for processing."""

    status: Literal["CREATED"] = "CREATED"
    timestamp: datetime = Field(default_factory=_utc_now)


class CompleteState(BaseModel, StopState):
    """Batch processing finished successfully."""

    status: Literal["COMPLETE"] = "COMPLETE"
    completed_at: datetime = Field(default_factory=_utc_now)


class SkippedState(BaseModel, StopState):
    """Batch skipped — nothing to process."""

    status: Literal["SKIPPED"] = "SKIPPED"
    skipped_at: datetime = Field(default_factory=_utc_now)
    reason: str


class FailedState(BaseModel, StopState):
    """Batch failed with an error."""

    status: Literal["FAILED"] = "FAILED"
    error_message: str
    failed_at: datetime = Field(default_factory=_utc_now)
    previous_status: str

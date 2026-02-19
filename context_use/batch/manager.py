from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from context_use.batch.models import BatchCategory, BatchStateMixin
from context_use.batch.states import (
    CurrentState,
    FailedState,
    NextState,
    RetryState,
    State,
    StopState,
)

logger = logging.getLogger(__name__)

MAX_POLL_ATTEMPTS = 500
MAX_RETRY_ATTEMPTS = 100


@dataclass
class ScheduleInstruction:
    """What the runner should do after a state transition.

    * ``stop=True``      → terminal, do not reschedule
    * ``countdown=None``  → reschedule immediately
    * ``countdown=N``     → reschedule after N seconds
    """

    stop: bool = False
    countdown: int | None = None


_category_manager_registry: dict[BatchCategory, type[BaseBatchManager]] = {}


def register_batch_manager(*categories: BatchCategory):
    """Decorator: register a manager class for one or more batch categories."""

    def decorator(cls: type[BaseBatchManager]) -> type[BaseBatchManager]:
        for cat in categories:
            _category_manager_registry[cat] = cls
        return cls

    return decorator


def get_manager_for_category(category: BatchCategory) -> type[BaseBatchManager]:
    cls = _category_manager_registry.get(category)
    if cls is None:
        raise ValueError(f"No manager registered for category: {category}")
    return cls


class BaseBatchManager(ABC):
    """State-machine orchestrator for a single batch.

    Sub-classes implement ``_transition`` which maps
    ``current_state → new_state | None``.
    """

    def __init__(self, batch: BatchStateMixin, db: AsyncSession) -> None:
        if not isinstance(batch, BatchStateMixin):
            raise TypeError(
                f"batch must be a BatchStateMixin, got {type(batch).__name__}"
            )
        self.batch = batch
        self.db = db

    @abstractmethod
    async def _transition(self, current_state: State) -> State | None:
        """Return the next state, or ``None`` to stop."""

    async def try_advance_state(self) -> ScheduleInstruction:
        """Advance one step and return what the runner should do next."""
        batch_id = self.batch.id
        current_status = self.batch.current_status
        try:
            current_state = self.batch.current_state
            new_state = await self._transition(current_state)

            if new_state is None:
                return ScheduleInstruction(stop=True)

            # Polling — same status returned means "still waiting"
            if isinstance(new_state, CurrentState) and type(new_state) is type(
                current_state
            ):
                new_state = new_state.increment_poll_count()
                logger.info(
                    "[%s] Polling (attempt %d)", batch_id, new_state.poll_count
                )
                if new_state.poll_count >= MAX_POLL_ATTEMPTS:
                    raise RuntimeError(
                        f"Polling exceeded {MAX_POLL_ATTEMPTS} attempts. "
                        f"State: {new_state.status}"
                    )

            # Retry — same status returned means "try again"
            elif isinstance(new_state, RetryState) and type(new_state) is type(
                current_state
            ):
                new_state = new_state.increment_retry_count()
                logger.info(
                    "[%s] Retry (attempt %d)", batch_id, new_state.retry_count
                )
                if new_state.retry_count > MAX_RETRY_ATTEMPTS:
                    raise RuntimeError(
                        f"Retry exceeded {MAX_RETRY_ATTEMPTS} attempts. "
                        f"State: {new_state.status}"
                    )

            # Persist
            self.batch.update_state(new_state)
            await self.db.commit()

            # Build scheduling instruction
            if isinstance(new_state, StopState):
                logger.info("[%s] Terminal state: %s", batch_id, new_state.status)
                return ScheduleInstruction(stop=True)

            if isinstance(new_state, CurrentState):
                countdown = new_state.poll_next_countdown
                logger.info("[%s] Poll in %ds", batch_id, countdown)
                return ScheduleInstruction(countdown=countdown)

            if isinstance(new_state, RetryState):
                countdown = new_state.retry_countdown
                logger.info("[%s] Retry in %ds", batch_id, countdown)
                return ScheduleInstruction(countdown=countdown)

            if isinstance(new_state, NextState):
                logger.info("[%s] Advancing immediately", batch_id)
                return ScheduleInstruction(countdown=None)

            raise ValueError(f"Unknown state base class for {new_state}")

        except Exception as exc:
            await self.db.rollback()
            logger.error(
                "[%s] Error advancing state: %s", batch_id, exc, exc_info=True
            )
            self.batch.update_state(
                FailedState(
                    error_message=str(exc),
                    previous_status=current_status,
                )
            )
            await self.db.commit()
            return ScheduleInstruction(stop=True)

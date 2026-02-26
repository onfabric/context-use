from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from context_use.batch.states import (
    CurrentState,
    FailedState,
    NextState,
    RetryState,
    State,
    StopState,
)
from context_use.models.batch import Batch, BatchCategory

if TYPE_CHECKING:
    from context_use.llm.base import BaseLLMClient
    from context_use.storage.base import StorageBackend
    from context_use.store.base import Store

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


@dataclass
class BatchContext:
    """Shared resources that batch managers need."""

    store: Store
    llm_client: BaseLLMClient
    storage: StorageBackend


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

    def __init__(self, batch: Batch, ctx: BatchContext) -> None:
        self.batch = batch
        self.ctx = ctx

    @abstractmethod
    async def _transition(self, current_state: State) -> State | None:
        """Return the next state, or ``None`` to stop."""

    async def try_advance_state(self) -> ScheduleInstruction:
        """Advance one step and return what the runner should do next."""
        batch_id = self.batch.id
        current_status = self.batch.current_status

        async with self.ctx.store.atomic():
            refreshed = await self.ctx.store.get_batch(batch_id)
            if refreshed is None:
                logger.error("[%s] Batch not found in store", batch_id)
                return ScheduleInstruction(stop=True)
            self.batch = refreshed

            try:
                current_state = self.batch.parse_current_state()
                new_state = await self._transition(current_state)

                if new_state is None:
                    return ScheduleInstruction(stop=True)

                if isinstance(new_state, CurrentState) and type(new_state) is type(
                    current_state
                ):
                    new_state = new_state.increment_poll_count()
                    logger.info(
                        "[%s] Polling (attempt %d)",
                        batch_id,
                        new_state.poll_count,
                    )
                    if new_state.poll_count >= MAX_POLL_ATTEMPTS:
                        raise RuntimeError(
                            f"Polling exceeded {MAX_POLL_ATTEMPTS} attempts. "
                            f"State: {new_state.status}"
                        )

                elif isinstance(new_state, RetryState) and type(new_state) is type(
                    current_state
                ):
                    new_state = new_state.increment_retry_count()
                    logger.info(
                        "[%s] Retry (attempt %d)",
                        batch_id,
                        new_state.retry_count,
                    )
                    if new_state.retry_count > MAX_RETRY_ATTEMPTS:
                        raise RuntimeError(
                            f"Retry exceeded {MAX_RETRY_ATTEMPTS} attempts. "
                            f"State: {new_state.status}"
                        )

                self.batch.push_state(new_state)
                await self.ctx.store.update_batch(self.batch)

            except Exception as exc:
                logger.error(
                    "[%s] Error advancing state: %s",
                    batch_id,
                    exc,
                    exc_info=True,
                )
                self.batch.push_state(
                    FailedState(
                        error_message=str(exc),
                        previous_status=current_status,
                    )
                )
                await self.ctx.store.update_batch(self.batch)
                return ScheduleInstruction(stop=True)

        final_state = self.batch.parse_current_state()
        if isinstance(final_state, StopState):
            logger.info("[%s] Terminal state: %s", batch_id, final_state.status)
            return ScheduleInstruction(stop=True)

        if isinstance(final_state, CurrentState):
            countdown = final_state.poll_next_countdown
            logger.info("[%s] Poll in %ds", batch_id, countdown)
            return ScheduleInstruction(countdown=countdown)

        if isinstance(final_state, RetryState):
            countdown = final_state.retry_countdown
            logger.info("[%s] Retry in %ds", batch_id, countdown)
            return ScheduleInstruction(countdown=countdown)

        if isinstance(final_state, NextState):
            logger.info("[%s] Advancing immediately", batch_id)
            return ScheduleInstruction(countdown=None)

        raise ValueError(f"Unknown state base class for {final_state}")

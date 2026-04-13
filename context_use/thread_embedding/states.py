# pyright: reportIncompatibleVariableOverride=false

from __future__ import annotations

import random
from datetime import datetime
from typing import Literal

from pydantic import Field

from context_use.batch.registry import register_batch_state_parser
from context_use.batch.states import (
    CompleteState,
    CreatedState,
    CurrentState,
    FailedState,
    NextState,
    SkippedState,
    State,
    _utc_now,
)
from context_use.models.batch import BatchCategory

THREAD_EMBED_POLL_INTERVAL_SECS = 10


class ThreadEmbedPendingState(CurrentState):
    status: Literal["THREAD_EMBED_PENDING"] = "THREAD_EMBED_PENDING"
    job_key: str
    submitted_at: datetime = Field(default_factory=_utc_now)

    @property
    def poll_next_countdown(self) -> int:
        jitter = random.randint(-5, 5)
        return max(0, THREAD_EMBED_POLL_INTERVAL_SECS + jitter)


class ThreadEmbedCompleteState(NextState):
    status: Literal["THREAD_EMBED_COMPLETE"] = "THREAD_EMBED_COMPLETE"
    completed_at: datetime = Field(default_factory=_utc_now)
    embedded_count: int = 0


ThreadEmbeddingBatchState = (
    CreatedState
    | ThreadEmbedPendingState
    | ThreadEmbedCompleteState
    | CompleteState
    | SkippedState
    | FailedState
)

_STATE_MAP: dict[str, type[State]] = {
    "CREATED": CreatedState,
    "THREAD_EMBED_PENDING": ThreadEmbedPendingState,
    "THREAD_EMBED_COMPLETE": ThreadEmbedCompleteState,
    "COMPLETE": CompleteState,
    "SKIPPED": SkippedState,
    "FAILED": FailedState,
}


@register_batch_state_parser(BatchCategory.thread_embedding)
def parse_thread_embedding_batch_state(state_dict: dict) -> State:
    status = state_dict.get("status")
    if status is None:
        raise ValueError("State dict missing 'status' key")
    cls = _STATE_MAP.get(status)
    if cls is None:
        raise ValueError(f"Unknown thread_embedding batch state: {status}")
    return cls.model_validate(state_dict)

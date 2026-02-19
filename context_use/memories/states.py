"""Pipeline-specific states for the memories pipeline."""
# pyright: reportIncompatibleVariableOverride=false
# Literal field overrides are the standard Pydantic discriminated-union pattern.
# pyright flags them as incompatible variable overrides, but this is a false
# positive for frozen/immutable models.

from __future__ import annotations

import random
from datetime import datetime
from typing import Literal

from pydantic import Field

from context_use.batch.models import BatchCategory, register_batch_state_parser
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

MEMORY_POLL_INTERVAL_SECS = 60


class MemoryGeneratePendingState(CurrentState):
    """LLM batch job submitted — polling for results."""

    status: Literal["MEMORY_GENERATE_PENDING"] = "MEMORY_GENERATE_PENDING"
    job_key: str
    submitted_at: datetime = Field(default_factory=_utc_now)

    @property
    def poll_next_countdown(self) -> int:
        jitter = random.randint(-10, 10)
        return max(0, MEMORY_POLL_INTERVAL_SECS + jitter)


class MemoryGenerateCompleteState(NextState):
    """LLM results received and stored in tapestry_memories."""

    status: Literal["MEMORY_GENERATE_COMPLETE"] = "MEMORY_GENERATE_COMPLETE"
    completed_at: datetime = Field(default_factory=_utc_now)
    memories_count: int = 0


class MemoryEmbedPendingState(CurrentState):
    """Embedding batch job submitted — polling for results."""

    status: Literal["MEMORY_EMBED_PENDING"] = "MEMORY_EMBED_PENDING"
    job_key: str
    submitted_at: datetime = Field(default_factory=_utc_now)

    @property
    def poll_next_countdown(self) -> int:
        jitter = random.randint(-10, 10)
        return max(0, MEMORY_POLL_INTERVAL_SECS + jitter)


class MemoryEmbedCompleteState(NextState):
    """Embeddings received and stored on tapestry_memories."""

    status: Literal["MEMORY_EMBED_COMPLETE"] = "MEMORY_EMBED_COMPLETE"
    completed_at: datetime = Field(default_factory=_utc_now)
    embedded_count: int = 0


MemoryBatchState = (
    CreatedState
    | MemoryGeneratePendingState
    | MemoryGenerateCompleteState
    | MemoryEmbedPendingState
    | MemoryEmbedCompleteState
    | CompleteState
    | SkippedState
    | FailedState
)

_state_map: dict[str, type[State]] = {
    "CREATED": CreatedState,
    "MEMORY_GENERATE_PENDING": MemoryGeneratePendingState,
    "MEMORY_GENERATE_COMPLETE": MemoryGenerateCompleteState,
    "MEMORY_EMBED_PENDING": MemoryEmbedPendingState,
    "MEMORY_EMBED_COMPLETE": MemoryEmbedCompleteState,
    "COMPLETE": CompleteState,
    "SKIPPED": SkippedState,
    "FAILED": FailedState,
}


@register_batch_state_parser(BatchCategory.memories)
def parse_memory_batch_state(state_dict: dict) -> State:
    status = state_dict.get("status")
    if status is None:
        raise ValueError("State dict missing 'status' key")
    cls = _state_map.get(status)
    if cls is None:
        raise ValueError(f"Unknown MemoryBatch state: {status}")
    return cls.model_validate(state_dict)

# pyright: reportIncompatibleVariableOverride=false
# Literal field overrides are the standard Pydantic discriminated-union pattern.
# pyright flags them as incompatible variable overrides, but this is a false
# positive for frozen/immutable models.

from __future__ import annotations

import enum
import random
from datetime import datetime
from typing import Literal

from pydantic import Field

from context_use.batch.registry import register_batch_state_parser
from context_use.batch.states import (
    BatchStatus,
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

MEMORY_POLL_INTERVAL_SECS = 10


class MemoryBatchStatus(enum.StrEnum):
    created = BatchStatus.created.value
    memory_generate_pending = "MEMORY_GENERATE_PENDING"
    memory_generate_complete = "MEMORY_GENERATE_COMPLETE"
    memory_embed_pending = "MEMORY_EMBED_PENDING"
    memory_embed_complete = "MEMORY_EMBED_COMPLETE"
    complete = BatchStatus.complete.value
    skipped = BatchStatus.skipped.value
    failed = BatchStatus.failed.value

    @classmethod
    def parse(cls, status: str) -> MemoryBatchStatus | None:
        try:
            return cls(status)
        except ValueError:
            return None


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
    created_memory_ids: list[str] = Field(default_factory=list)


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
    MemoryBatchStatus.created.value: CreatedState,
    MemoryBatchStatus.memory_generate_pending.value: MemoryGeneratePendingState,
    MemoryBatchStatus.memory_generate_complete.value: MemoryGenerateCompleteState,
    MemoryBatchStatus.memory_embed_pending.value: MemoryEmbedPendingState,
    MemoryBatchStatus.memory_embed_complete.value: MemoryEmbedCompleteState,
    MemoryBatchStatus.complete.value: CompleteState,
    MemoryBatchStatus.skipped.value: SkippedState,
    MemoryBatchStatus.failed.value: FailedState,
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

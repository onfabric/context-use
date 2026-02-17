"""Pipeline-specific states for the memory-candidates pipeline.

State machine:
    CREATED → MEMORY_GENERATE_PENDING → MEMORY_GENERATE_COMPLETE → COMPLETE

Portable: identical between context-use and aertex.
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Literal, Union

from pydantic import BaseModel, Field

from context_use.batch.models import BatchCategory, register_batch_state_parser
from context_use.batch.states import (
    CompleteState,
    CreatedState,
    CurrentState,
    FailedState,
    NextState,
    SkippedState,
    _utc_now,
)

MEMORY_POLL_INTERVAL_SECS = 60


class MemoryGeneratePendingState(BaseModel, CurrentState):
    """LLM batch job submitted — polling for results."""

    status: Literal["MEMORY_GENERATE_PENDING"] = "MEMORY_GENERATE_PENDING"
    job_key: str
    submitted_at: datetime = Field(default_factory=_utc_now)

    @property
    def poll_next_countdown(self) -> int:
        jitter = random.randint(-10, 10)
        return max(0, MEMORY_POLL_INTERVAL_SECS + jitter)


class MemoryGenerateCompleteState(BaseModel, NextState):
    """LLM results received and stored in tapestry_memories."""

    status: Literal["MEMORY_GENERATE_COMPLETE"] = "MEMORY_GENERATE_COMPLETE"
    completed_at: datetime = Field(default_factory=_utc_now)
    memories_count: int = 0


# ---------------------------------------------------------------------------
# State parser registration
# ---------------------------------------------------------------------------

MemoryCandidateBatchState = Union[
    CreatedState,
    MemoryGeneratePendingState,
    MemoryGenerateCompleteState,
    CompleteState,
    SkippedState,
    FailedState,
]

_state_map: dict[str, type[BaseModel]] = {
    "CREATED": CreatedState,
    "MEMORY_GENERATE_PENDING": MemoryGeneratePendingState,
    "MEMORY_GENERATE_COMPLETE": MemoryGenerateCompleteState,
    "COMPLETE": CompleteState,
    "SKIPPED": SkippedState,
    "FAILED": FailedState,
}


@register_batch_state_parser(BatchCategory.memory_candidates)
def parse_memory_candidate_batch_state(state_dict: dict) -> MemoryCandidateBatchState:
    status = state_dict.get("status")
    cls = _state_map.get(status)  # type: ignore[arg-type]
    if cls is None:
        raise ValueError(f"Unknown MemoryCandidateBatch state: {status}")
    return cls.model_validate(state_dict)

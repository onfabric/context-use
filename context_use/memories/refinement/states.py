# pyright: reportIncompatibleVariableOverride=false
# Literal field overrides are the standard Pydantic discriminated-union pattern.

from __future__ import annotations

import random
from datetime import datetime
from typing import Literal

from pydantic import Field

from context_use.batch.models import register_batch_state_parser
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

REFINEMENT_POLL_INTERVAL_SECS = 10


class RefinementCreatedState(NextState):
    """Initial state for refinement batches — carries seed memory IDs."""

    status: Literal["REFINEMENT_CREATED"] = "REFINEMENT_CREATED"
    seed_memory_ids: list[str]
    timestamp: datetime = Field(default_factory=_utc_now)


class RefinementDiscoverState(NextState):
    """Discovery complete — clusters identified for refinement."""

    status: Literal["REFINEMENT_DISCOVER"] = "REFINEMENT_DISCOVER"
    clusters: dict[str, list[str]]
    cluster_count: int
    discovered_at: datetime = Field(default_factory=_utc_now)


class RefinementPendingState(CurrentState):
    """LLM refinement batch submitted — polling for results."""

    status: Literal["REFINEMENT_PENDING"] = "REFINEMENT_PENDING"
    job_key: str
    submitted_at: datetime = Field(default_factory=_utc_now)

    @property
    def poll_next_countdown(self) -> int:
        jitter = random.randint(-10, 10)
        return max(0, REFINEMENT_POLL_INTERVAL_SECS + jitter)


class RefinementCompleteState(NextState):
    """LLM refinement results stored, inputs superseded."""

    status: Literal["REFINEMENT_COMPLETE"] = "REFINEMENT_COMPLETE"
    completed_at: datetime = Field(default_factory=_utc_now)
    refined_count: int = 0
    superseded_count: int = 0
    created_memory_ids: list[str] = Field(default_factory=list)


class RefinementEmbedPendingState(CurrentState):
    """Embedding batch for refined memories submitted — polling."""

    status: Literal["REFINEMENT_EMBED_PENDING"] = "REFINEMENT_EMBED_PENDING"
    job_key: str
    submitted_at: datetime = Field(default_factory=_utc_now)

    @property
    def poll_next_countdown(self) -> int:
        jitter = random.randint(-10, 10)
        return max(0, REFINEMENT_POLL_INTERVAL_SECS + jitter)


class RefinementEmbedCompleteState(NextState):
    """Embeddings for refined memories stored."""

    status: Literal["REFINEMENT_EMBED_COMPLETE"] = "REFINEMENT_EMBED_COMPLETE"
    completed_at: datetime = Field(default_factory=_utc_now)
    embedded_count: int = 0


RefinementBatchState = (
    CreatedState
    | RefinementCreatedState
    | RefinementDiscoverState
    | RefinementPendingState
    | RefinementCompleteState
    | RefinementEmbedPendingState
    | RefinementEmbedCompleteState
    | CompleteState
    | SkippedState
    | FailedState
)

_state_map: dict[str, type[State]] = {
    "CREATED": CreatedState,
    "REFINEMENT_CREATED": RefinementCreatedState,
    "REFINEMENT_DISCOVER": RefinementDiscoverState,
    "REFINEMENT_PENDING": RefinementPendingState,
    "REFINEMENT_COMPLETE": RefinementCompleteState,
    "REFINEMENT_EMBED_PENDING": RefinementEmbedPendingState,
    "REFINEMENT_EMBED_COMPLETE": RefinementEmbedCompleteState,
    "COMPLETE": CompleteState,
    "SKIPPED": SkippedState,
    "FAILED": FailedState,
}


@register_batch_state_parser(BatchCategory.refinement)
def parse_refinement_batch_state(state_dict: dict) -> State:
    status = state_dict.get("status")
    if status is None:
        raise ValueError("State dict missing 'status' key")
    cls = _state_map.get(status)
    if cls is None:
        raise ValueError(f"Unknown RefinementBatch state: {status}")
    return cls.model_validate(state_dict)

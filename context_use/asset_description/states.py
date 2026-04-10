# pyright: reportIncompatibleVariableOverride=false
# Literal field overrides are the standard Pydantic discriminated-union pattern.

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
    _utc_now,
)
from context_use.models.batch import BatchCategory

DESC_POLL_INTERVAL_SECS = 30


class DescGeneratePendingState(CurrentState):
    status: Literal["DESC_GENERATE_PENDING"] = "DESC_GENERATE_PENDING"
    job_key: str
    submitted_at: datetime = Field(default_factory=_utc_now)

    @property
    def poll_next_countdown(self) -> int:
        jitter = random.randint(-10, 10)
        return max(0, DESC_POLL_INTERVAL_SECS + jitter)


class DescGenerateCompleteState(NextState):
    status: Literal["DESC_GENERATE_COMPLETE"] = "DESC_GENERATE_COMPLETE"
    completed_at: datetime = Field(default_factory=_utc_now)
    descriptions_count: int = 0


AssetDescriptionBatchState = (
    CreatedState
    | DescGeneratePendingState
    | DescGenerateCompleteState
    | CompleteState
    | SkippedState
    | FailedState
)

_STATE_MAP: dict[str, type[AssetDescriptionBatchState]] = {  # type: ignore[type-arg]
    "CREATED": CreatedState,
    "DESC_GENERATE_PENDING": DescGeneratePendingState,
    "DESC_GENERATE_COMPLETE": DescGenerateCompleteState,
    "COMPLETE": CompleteState,
    "SKIPPED": SkippedState,
    "FAILED": FailedState,
}


@register_batch_state_parser(BatchCategory.asset_description)
def parse_asset_description_batch_state(state_dict: dict) -> AssetDescriptionBatchState:  # type: ignore[return]
    status = state_dict.get("status")
    state_class = _STATE_MAP.get(status)  # type: ignore[arg-type]
    if not state_class:
        raise ValueError(f"Unknown asset_description batch state status: {status}")
    return state_class.model_validate(state_dict)

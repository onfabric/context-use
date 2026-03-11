from __future__ import annotations

from context_use.batch.states import CompleteState, CreatedState, FailedState
from context_use.cli.base import _batch_detail_from_state, _safe_current_state
from context_use.memories.states import (
    MemoryEmbedCompleteState,
    MemoryGenerateCompleteState,
)
from context_use.models.batch import Batch


class TestBatchDetailFromState:
    def test_none_returns_empty(self) -> None:
        assert _batch_detail_from_state(None) == ""

    def test_created_returns_empty(self) -> None:
        assert _batch_detail_from_state(CreatedState()) == ""

    def test_failed_returns_first_line_of_error(self) -> None:
        state = FailedState(error_message="line1\nline2", previous_status="CREATED")
        assert _batch_detail_from_state(state) == "line1"

    def test_failed_empty_message_returns_empty(self) -> None:
        state = FailedState(error_message="", previous_status="CREATED")
        assert _batch_detail_from_state(state) == ""

    def test_memory_generate_complete_with_count(self) -> None:
        state = MemoryGenerateCompleteState(memories_count=5)
        assert _batch_detail_from_state(state) == "5 memories generated"

    def test_memory_generate_complete_with_ids(self) -> None:
        state = MemoryGenerateCompleteState(created_memory_ids=["a", "b"])
        assert _batch_detail_from_state(state) == "2 memories stored"

    def test_memory_generate_complete_empty(self) -> None:
        state = MemoryGenerateCompleteState()
        assert _batch_detail_from_state(state) == ""

    def test_memory_embed_complete(self) -> None:
        state = MemoryEmbedCompleteState(embedded_count=10)
        assert _batch_detail_from_state(state) == "10 memories embedded"

    def test_complete_returns_empty(self) -> None:
        assert _batch_detail_from_state(CompleteState()) == ""


class TestSafeCurrentState:
    def test_returns_parsed_state(self) -> None:
        batch = Batch(
            batch_number=1,
            category="memories",
            states=[{"status": "CREATED"}],
        )
        state = _safe_current_state(batch)
        assert isinstance(state, CreatedState)

    def test_falls_back_to_created_on_error(self) -> None:
        batch = Batch(
            batch_number=1,
            category="memories",
            states=[],
        )
        state = _safe_current_state(batch)
        assert isinstance(state, CreatedState)

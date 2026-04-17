from __future__ import annotations

from context_use.batch.states import (
    CompleteState,
    CreatedState,
    FailedState,
    SkippedState,
)
from context_use.thread_embedding.states import (
    ThreadEmbedCompleteState,
    ThreadEmbedPendingState,
    parse_thread_embedding_batch_state,
)


class TestParseThreadEmbeddingBatchState:
    def test_created(self) -> None:
        state = parse_thread_embedding_batch_state({"status": "CREATED"})
        assert isinstance(state, CreatedState)

    def test_embed_pending(self) -> None:
        state = parse_thread_embedding_batch_state(
            {"status": "THREAD_EMBED_PENDING", "job_key": "job-1"}
        )
        assert isinstance(state, ThreadEmbedPendingState)
        assert state.job_key == "job-1"

    def test_embed_complete(self) -> None:
        state = parse_thread_embedding_batch_state(
            {"status": "THREAD_EMBED_COMPLETE", "embedded_count": 5}
        )
        assert isinstance(state, ThreadEmbedCompleteState)
        assert state.embedded_count == 5

    def test_complete(self) -> None:
        state = parse_thread_embedding_batch_state({"status": "COMPLETE"})
        assert isinstance(state, CompleteState)

    def test_skipped(self) -> None:
        state = parse_thread_embedding_batch_state(
            {"status": "SKIPPED", "reason": "empty"}
        )
        assert isinstance(state, SkippedState)

    def test_failed(self) -> None:
        state = parse_thread_embedding_batch_state(
            {"status": "FAILED", "error_message": "boom", "previous_status": "CREATED"}
        )
        assert isinstance(state, FailedState)

    def test_unknown_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="Unknown thread_embedding"):
            parse_thread_embedding_batch_state({"status": "BOGUS"})


class TestThreadEmbedPendingState:
    def test_poll_countdown_is_non_negative(self) -> None:
        state = ThreadEmbedPendingState(job_key="job-1")
        assert state.poll_next_countdown >= 0

    def test_round_trip(self) -> None:
        state = ThreadEmbedPendingState(job_key="job-1")
        dumped = state.model_dump(mode="json")
        restored = parse_thread_embedding_batch_state(dumped)
        assert isinstance(restored, ThreadEmbedPendingState)
        assert restored.job_key == "job-1"

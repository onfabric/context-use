from __future__ import annotations

import pytest

from context_use.batch.states import (
    CompleteState,
    CreatedState,
    FailedState,
    SkippedState,
)
from context_use.thread_embedding.states import (
    THREAD_EMBED_POLL_INTERVAL_SECS,
    ThreadEmbedCompleteState,
    ThreadEmbedPendingState,
    parse_thread_embedding_batch_state,
)


class TestStateParsingRoundTrip:
    @pytest.mark.parametrize(
        "state",
        [
            CreatedState(),
            ThreadEmbedPendingState(job_key="job-1"),
            ThreadEmbedCompleteState(embedded_count=5),
            CompleteState(),
            SkippedState(reason="nothing"),
            FailedState(error_message="boom", previous_status="CREATED"),
        ],
    )
    def test_round_trip(self, state) -> None:
        serialized = state.model_dump(mode="json")
        parsed = parse_thread_embedding_batch_state(serialized)
        assert type(parsed) is type(state)
        assert parsed.status == state.status

    def test_raises_on_missing_status(self) -> None:
        with pytest.raises(ValueError, match="missing 'status'"):
            parse_thread_embedding_batch_state({})

    def test_raises_on_unknown_status(self) -> None:
        with pytest.raises(ValueError, match="Unknown"):
            parse_thread_embedding_batch_state({"status": "BANANA"})


class TestPollNextCountdown:
    def test_returns_reasonable_value(self) -> None:
        state = ThreadEmbedPendingState(job_key="job-1")
        countdown = state.poll_next_countdown
        assert countdown >= 0
        assert countdown <= THREAD_EMBED_POLL_INTERVAL_SECS + 5

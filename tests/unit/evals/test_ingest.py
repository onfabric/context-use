from __future__ import annotations

from pathlib import Path

import pytest

from context_use.etl.payload.models import CURRENT_THREAD_PAYLOAD_VERSION
from evals.longmemeval.dataset import LongMemEvalDataset
from evals.longmemeval.ingest import (
    INTERACTION_TYPE,
    PROVIDER,
    question_to_thread_rows,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures/evals/longmemeval/sample.json"
)


@pytest.fixture
def dataset() -> LongMemEvalDataset:
    return LongMemEvalDataset.from_file(FIXTURE_PATH)


class TestQuestionToThreadRows:
    def test_returns_rows_for_all_turns(self, dataset: LongMemEvalDataset) -> None:
        q = dataset["q001"]
        rows = question_to_thread_rows(q)
        total_turns = sum(len(s) for s in q.haystack_sessions)
        assert len(rows) == total_turns

    def test_row_provider_and_interaction_type(
        self, dataset: LongMemEvalDataset
    ) -> None:
        rows = question_to_thread_rows(dataset["q001"])
        for row in rows:
            assert row.provider == PROVIDER
            assert row.interaction_type == INTERACTION_TYPE

    def test_row_version(self, dataset: LongMemEvalDataset) -> None:
        rows = question_to_thread_rows(dataset["q001"])
        for row in rows:
            assert row.version == CURRENT_THREAD_PAYLOAD_VERSION

    def test_unique_keys_are_distinct(self, dataset: LongMemEvalDataset) -> None:
        rows = question_to_thread_rows(dataset["q002"])
        keys = [r.unique_key for r in rows]
        assert len(keys) == len(set(keys))

    def test_payload_has_fibre_kind(self, dataset: LongMemEvalDataset) -> None:
        rows = question_to_thread_rows(dataset["q001"])
        for row in rows:
            assert "fibreKind" in row.payload
            assert row.payload["fibreKind"] in ("SendMessage", "ReceiveMessage")

    def test_send_vs_receive_mapping(self, dataset: LongMemEvalDataset) -> None:
        q = dataset["q001"]
        rows = question_to_thread_rows(q)
        user_turns = [t for s in q.haystack_sessions for t in s if t.role == "user"]
        send_rows = [r for r in rows if r.payload["fibreKind"] == "SendMessage"]
        assert len(send_rows) == len(user_turns)

    def test_collection_context_contains_session_id(
        self, dataset: LongMemEvalDataset
    ) -> None:
        q = dataset["q001"]
        rows = question_to_thread_rows(q)
        first_row = rows[0]
        obj = first_row.payload.get("object", {})
        ctx = obj.get("context", {})
        assert ctx.get("id") == "https://longmemeval.bench/session_001"

    def test_asat_uses_session_date(self, dataset: LongMemEvalDataset) -> None:
        q = dataset["q001"]
        rows = question_to_thread_rows(q)
        assert rows[0].asat.strftime("%Y-%m-%d") == "2024-03-10"

    def test_preview_is_nonempty(self, dataset: LongMemEvalDataset) -> None:
        rows = question_to_thread_rows(dataset["q001"])
        for row in rows:
            assert row.preview

    def test_empty_sessions(self) -> None:
        from evals.longmemeval.schema import Question

        q = Question(
            question_id="empty",
            question="test",
            question_type="test",
            answer="test",
            haystack_sessions=[],
        )
        assert question_to_thread_rows(q) == []

    def test_fallback_session_ids(self) -> None:
        from evals.longmemeval.schema import Question, Turn

        q = Question(
            question_id="no_ids",
            question="test",
            question_type="test",
            answer="test",
            haystack_sessions=[
                [Turn(role="user", content="hello")],
            ],
            haystack_session_ids=[],
            haystack_dates=[],
        )
        rows = question_to_thread_rows(q)
        assert len(rows) == 1
        obj = rows[0].payload.get("object", {})
        ctx = obj.get("context", {})
        assert ctx.get("id") == "https://longmemeval.bench/session_0"

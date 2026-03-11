from __future__ import annotations

from pathlib import Path

import pytest

from context_use.evals.longmemeval.dataset import LongMemEvalDataset

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures/evals/longmemeval/sample.json"
)


@pytest.fixture
def dataset() -> LongMemEvalDataset:
    return LongMemEvalDataset.from_file(FIXTURE_PATH)


class TestLongMemEvalDataset:
    def test_loads_all_questions(self, dataset: LongMemEvalDataset) -> None:
        assert len(dataset) == 4

    def test_question_ids(self, dataset: LongMemEvalDataset) -> None:
        ids = [q.question_id for q in dataset.questions]
        assert ids == ["q001", "q002", "q003_abs", "q004"]

    def test_getitem_by_id(self, dataset: LongMemEvalDataset) -> None:
        q = dataset["q001"]
        assert q.question_type == "single-session-user"
        assert q.answer == "Python"

    def test_getitem_missing_raises(self, dataset: LongMemEvalDataset) -> None:
        with pytest.raises(KeyError):
            dataset["nonexistent"]

    def test_filter_by_type(self, dataset: LongMemEvalDataset) -> None:
        filtered = dataset.filter_by_type("abstention")
        assert len(filtered) == 1
        assert filtered.questions[0].question_id == "q003_abs"

    def test_question_types(self, dataset: LongMemEvalDataset) -> None:
        types = dataset.question_types
        assert "abstention" in types
        assert "single-session-user" in types
        assert "multi-session" in types
        assert "knowledge-update" in types

    def test_haystack_sessions_structure(self, dataset: LongMemEvalDataset) -> None:
        q = dataset["q002"]
        assert len(q.haystack_sessions) == 3
        assert len(q.haystack_session_ids) == 3
        assert len(q.haystack_dates) == 3
        assert q.haystack_sessions[0][0].role == "user"
        assert q.haystack_sessions[0][0].has_answer is True

    def test_is_abstention(self, dataset: LongMemEvalDataset) -> None:
        assert dataset["q003_abs"].is_abstention is True
        assert dataset["q001"].is_abstention is False

    def test_correct_docs(self, dataset: LongMemEvalDataset) -> None:
        assert dataset["q001"].correct_docs == [0]
        assert dataset["q002"].correct_docs == [0, 1]
        assert dataset["q003_abs"].correct_docs == []

    def test_answer_session_ids(self, dataset: LongMemEvalDataset) -> None:
        assert dataset["q002"].answer_session_ids == ["session_010", "session_011"]
        assert dataset["q003_abs"].answer_session_ids == []

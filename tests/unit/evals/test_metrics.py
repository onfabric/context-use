from __future__ import annotations

from evals.metrics import compute_metrics
from evals.types import EvalResult, JudgeVerdict


def _make_result(
    qid: str,
    qtype: str,
    label: str,
) -> EvalResult:
    return EvalResult(
        question_id=qid,
        question_type=qtype,
        hypothesis="h",
        reference="r",
        verdict=JudgeVerdict(label=label, reasoning="test"),
    )


class TestComputeMetrics:
    def test_overall_accuracy(self) -> None:
        results = [
            _make_result("q1", "type_a", "CORRECT"),
            _make_result("q2", "type_a", "CORRECT"),
            _make_result("q3", "type_b", "INCORRECT"),
            _make_result("q4", "type_b", "CORRECT"),
        ]
        metrics = compute_metrics(results)
        assert metrics.total == 4
        assert metrics.correct == 3
        assert metrics.accuracy == 0.75

    def test_by_type_breakdown(self) -> None:
        results = [
            _make_result("q1", "type_a", "CORRECT"),
            _make_result("q2", "type_a", "INCORRECT"),
            _make_result("q3", "type_b", "CORRECT"),
        ]
        metrics = compute_metrics(results)
        assert "type_a" in metrics.by_type
        assert metrics.by_type["type_a"].total == 2
        assert metrics.by_type["type_a"].correct == 1
        assert metrics.by_type["type_a"].accuracy == 0.5
        assert metrics.by_type["type_b"].accuracy == 1.0

    def test_empty_results(self) -> None:
        metrics = compute_metrics([])
        assert metrics.total == 0
        assert metrics.correct == 0
        assert metrics.accuracy == 0.0
        assert metrics.by_type == {}

    def test_skips_unjudged_results(self) -> None:
        results = [
            _make_result("q1", "type_a", "CORRECT"),
            EvalResult(
                question_id="q2",
                question_type="type_a",
                hypothesis="h",
                reference="r",
                verdict=None,
            ),
        ]
        metrics = compute_metrics(results)
        assert metrics.total == 1
        assert metrics.correct == 1

    def test_all_incorrect(self) -> None:
        results = [
            _make_result("q1", "t", "INCORRECT"),
            _make_result("q2", "t", "INCORRECT"),
        ]
        metrics = compute_metrics(results)
        assert metrics.accuracy == 0.0
        assert metrics.by_type["t"].accuracy == 0.0

    def test_type_metrics_properties(self) -> None:
        results = [_make_result("q1", "t", "CORRECT")]
        metrics = compute_metrics(results)
        tm = metrics.by_type["t"]
        assert tm.question_type == "t"
        assert tm.total == 1
        assert tm.correct == 1
        assert tm.accuracy == 1.0

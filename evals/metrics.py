from __future__ import annotations

from collections import defaultdict

from evals.types import EvalMetrics, EvalResult, TypeMetrics


def compute_metrics(results: list[EvalResult]) -> EvalMetrics:
    """Aggregate evaluation results into overall and per-type accuracy."""
    judged = [r for r in results if r.verdict is not None]
    total = len(judged)
    correct = sum(1 for r in judged if r.verdict and r.verdict.label == "CORRECT")

    by_type_counts: dict[str, list[EvalResult]] = defaultdict(list)
    for r in judged:
        by_type_counts[r.question_type].append(r)

    by_type: dict[str, TypeMetrics] = {}
    for qtype, type_results in sorted(by_type_counts.items()):
        type_total = len(type_results)
        type_correct = sum(
            1 for r in type_results if r.verdict and r.verdict.label == "CORRECT"
        )
        by_type[qtype] = TypeMetrics(
            question_type=qtype,
            total=type_total,
            correct=type_correct,
        )

    return EvalMetrics(total=total, correct=correct, by_type=by_type)

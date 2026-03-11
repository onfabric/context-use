from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class JudgeVerdict:
    label: str
    reasoning: str


@dataclass
class EvalResult:
    question_id: str
    question_type: str
    hypothesis: str
    reference: str
    verdict: JudgeVerdict | None = None


@dataclass(frozen=True)
class TypeMetrics:
    question_type: str
    total: int
    correct: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total > 0 else 0.0


@dataclass(frozen=True)
class EvalMetrics:
    total: int
    correct: int
    by_type: dict[str, TypeMetrics] = field(default_factory=dict)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total > 0 else 0.0

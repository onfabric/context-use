from __future__ import annotations

import json
from pathlib import Path

from evals.longmemeval.schema import Question


class LongMemEvalDataset:
    """Loads and provides access to LongMemEval benchmark data.

    Accepts either the cleaned or original JSON files from
    ``xiaowu0162/longmemeval-cleaned`` on HuggingFace.
    """

    def __init__(self, questions: list[Question]) -> None:
        self._questions = questions
        self._by_id = {q.question_id: q for q in questions}

    @classmethod
    def from_file(cls, path: str | Path) -> LongMemEvalDataset:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        questions = [Question.model_validate(item) for item in raw]
        return cls(questions)

    @property
    def questions(self) -> list[Question]:
        return list(self._questions)

    def __len__(self) -> int:
        return len(self._questions)

    def __getitem__(self, question_id: str) -> Question:
        return self._by_id[question_id]

    def filter_by_type(self, question_type: str) -> LongMemEvalDataset:
        return LongMemEvalDataset(
            [q for q in self._questions if q.question_type == question_type]
        )

    @property
    def question_types(self) -> list[str]:
        return sorted({q.question_type for q in self._questions})

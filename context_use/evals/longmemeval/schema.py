from __future__ import annotations

from pydantic import BaseModel, Field


class Turn(BaseModel):
    role: str
    content: str
    has_answer: bool | None = None


class Question(BaseModel):
    """A single LongMemEval question with its haystack sessions.

    Fields mirror the upstream dataset at
    ``xiaowu0162/longmemeval-cleaned`` on HuggingFace.
    """

    question_id: str
    question: str
    question_type: str
    answer: str
    question_date: str | None = None
    haystack_sessions: list[list[Turn]]
    haystack_session_ids: list[str] = Field(default_factory=list)
    haystack_dates: list[str] = Field(default_factory=list)
    answer_session_ids: list[str] = Field(default_factory=list)
    correct_docs: list[int] = Field(default_factory=list)

    @property
    def is_abstention(self) -> bool:
        return self.question_id.endswith("_abs")

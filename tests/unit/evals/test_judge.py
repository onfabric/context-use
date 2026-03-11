from __future__ import annotations

import pytest
from pydantic import BaseModel

from context_use.evals.judge import JUDGE_PROMPT, LLMJudge, _JudgeSchema
from context_use.llm.base import BaseLLMClient, PromptItem


class _FakeLLMClient(BaseLLMClient):
    """Minimal stub that returns a canned judge response."""

    def __init__(self, verdict: str = "CORRECT", reasoning: str = "Matches.") -> None:
        self._verdict = verdict
        self._reasoning = reasoning

    async def batch_submit(self, batch_id: str, prompts: list[PromptItem]) -> str:
        raise NotImplementedError

    async def batch_get_results(self, job_key: str, schema: type[BaseModel]) -> None:
        return None

    async def embed_batch_submit(self, batch_id: str, items: list) -> str:
        raise NotImplementedError

    async def embed_batch_get_results(self, job_key: str) -> None:
        return None

    async def completion(self, prompt: str) -> str:
        return self._verdict

    async def structured_completion(
        self, prompt: PromptItem, schema: type[BaseModel]
    ) -> BaseModel:
        return _JudgeSchema(reasoning=self._reasoning, verdict=self._verdict)

    async def embed_query(self, text: str) -> list[float]:
        return [0.0] * 10


class TestLLMJudge:
    @pytest.mark.asyncio
    async def test_correct_verdict(self) -> None:
        client = _FakeLLMClient(verdict="CORRECT", reasoning="Answer matches.")
        judge = LLMJudge(client)
        verdict = await judge.judge(
            question="What color?",
            reference="Blue",
            hypothesis="Blue",
        )
        assert verdict.label == "CORRECT"
        assert verdict.reasoning == "Answer matches."

    @pytest.mark.asyncio
    async def test_incorrect_verdict(self) -> None:
        client = _FakeLLMClient(verdict="INCORRECT", reasoning="Wrong answer.")
        judge = LLMJudge(client)
        verdict = await judge.judge(
            question="What color?",
            reference="Blue",
            hypothesis="Red",
        )
        assert verdict.label == "INCORRECT"

    @pytest.mark.asyncio
    async def test_normalizes_unexpected_label(self) -> None:
        client = _FakeLLMClient(verdict="maybe", reasoning="Unsure.")
        judge = LLMJudge(client)
        verdict = await judge.judge(question="q", reference="a", hypothesis="b")
        assert verdict.label == "INCORRECT"

    def test_prompt_contains_placeholders(self) -> None:
        formatted = JUDGE_PROMPT.format(question="Q", reference="R", hypothesis="H")
        assert "Q" in formatted
        assert "R" in formatted
        assert "H" in formatted

    def test_judge_schema_fields(self) -> None:
        schema = _JudgeSchema.model_json_schema()
        assert "reasoning" in schema["properties"]
        assert "verdict" in schema["properties"]

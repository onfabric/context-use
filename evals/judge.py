from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from evals.types import JudgeVerdict
from context_use.llm.base import PromptItem

if TYPE_CHECKING:
    from context_use.llm.base import BaseLLMClient


JUDGE_PROMPT = """\
You are an impartial judge evaluating a question-answering system's response.

**Question:** {question}

**Reference answer:** {reference}

**System's answer:** {hypothesis}

Determine whether the system's answer is correct by comparing it to the \
reference answer. The system's answer does not need to match the reference \
word-for-word — it is correct if it conveys the same essential information.

For abstention questions (where the reference says the information is not \
available or unknown), the system should indicate it cannot answer. Giving \
a fabricated answer to an abstention question is incorrect.

Provide your reasoning, then give a final verdict."""


class _JudgeSchema(BaseModel):
    reasoning: str = Field(description="Brief explanation of the judgment")
    verdict: str = Field(description="CORRECT or INCORRECT")


class LLMJudge:
    """Uses an LLM to judge whether a hypothesis correctly answers a question."""

    def __init__(self, llm_client: BaseLLMClient) -> None:
        self._llm_client = llm_client

    async def judge(
        self,
        question: str,
        reference: str,
        hypothesis: str,
    ) -> JudgeVerdict:
        prompt_text = JUDGE_PROMPT.format(
            question=question,
            reference=reference,
            hypothesis=hypothesis,
        )
        prompt_item = PromptItem(
            item_id="judge",
            prompt=prompt_text,
            response_schema=_JudgeSchema.model_json_schema(),
        )
        result = await self._llm_client.structured_completion(prompt_item, _JudgeSchema)
        label = result.verdict.strip().upper()
        if label not in ("CORRECT", "INCORRECT"):
            label = "INCORRECT"
        return JudgeVerdict(label=label, reasoning=result.reasoning)

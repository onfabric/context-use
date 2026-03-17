from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from context_use.eval.llm_judge import (
    MemoryJudgment,
    SynthesisProbeResult,
    judge_memories,
    synthesis_probe,
)
from context_use.memories.prompt.base import Memory


def _mem(content: str, from_date: str = "2024-06-01", to_date: str = "2024-06-01") -> Memory:
    return Memory(content=content, from_date=from_date, to_date=to_date)


class TestSynthesisProbe:
    @pytest.mark.asyncio
    async def test_returns_probe_result(self) -> None:
        llm = AsyncMock()
        llm.completion.return_value = (
            "This person works at Acme Corp in Berlin. "
            "They run 3 times a week and use Strava to track runs."
        )
        memories = [
            _mem("I work at Acme Corp in Berlin on Kubernetes infrastructure."),
            _mem("I run 3 times a week and track on Strava."),
        ]

        result = await synthesis_probe(memories, llm)

        assert isinstance(result, SynthesisProbeResult)
        assert result.entity_count > 0
        assert result.word_count > 0
        assert result.entity_rate > 0
        assert "Acme" in result.profile
        llm.completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_memories(self) -> None:
        llm = AsyncMock()
        llm.completion.return_value = "No information available."

        result = await synthesis_probe([], llm)

        assert result.word_count > 0


class TestJudgeMemories:
    @pytest.mark.asyncio
    async def test_parses_judgments(self) -> None:
        llm = AsyncMock()
        llm.completion.return_value = '[{"index": 0, "score": 4}, {"index": 1, "score": 2}]'

        memories = [
            _mem("I debugged a Kubernetes pod restart loop at Acme Corp."),
            _mem("Had a productive session exploring ideas."),
        ]

        judgments = await judge_memories(memories, llm, batch_size=10)

        assert len(judgments) == 2
        assert judgments[0] == MemoryJudgment(index=0, score=4)
        assert judgments[1] == MemoryJudgment(index=1, score=2)

    @pytest.mark.asyncio
    async def test_handles_markdown_fenced_response(self) -> None:
        llm = AsyncMock()
        llm.completion.return_value = '```json\n[{"index": 0, "score": 3}]\n```'

        memories = [_mem("I tested Docker containers.")]
        judgments = await judge_memories(memories, llm, batch_size=10)

        assert len(judgments) == 1
        assert judgments[0].score == 3

    @pytest.mark.asyncio
    async def test_clamps_scores_to_1_5(self) -> None:
        llm = AsyncMock()
        llm.completion.return_value = '[{"index": 0, "score": 0}, {"index": 1, "score": 7}]'

        memories = [_mem("Low"), _mem("High")]
        judgments = await judge_memories(memories, llm, batch_size=10)

        assert judgments[0].score == 1
        assert judgments[1].score == 5

    @pytest.mark.asyncio
    async def test_handles_llm_failure_gracefully(self) -> None:
        llm = AsyncMock()
        llm.completion.side_effect = RuntimeError("API down")

        memories = [_mem("test")]
        judgments = await judge_memories(memories, llm, batch_size=10)

        assert judgments == []

    @pytest.mark.asyncio
    async def test_batches_large_sets(self) -> None:
        llm = AsyncMock()
        llm.completion.side_effect = [
            '[{"index": 0, "score": 3}, {"index": 1, "score": 4}]',
            '[{"index": 0, "score": 5}]',
        ]

        memories = [_mem(f"Memory {i}") for i in range(3)]
        judgments = await judge_memories(memories, llm, batch_size=2)

        assert len(judgments) == 3
        assert llm.completion.call_count == 2
        assert judgments[2].index == 2
        assert judgments[2].score == 5

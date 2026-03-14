from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from evals.longmemeval.dataset import LongMemEvalDataset
from evals.longmemeval.runner import LongMemEvalRunner, RunConfig
from context_use.llm.base import (
    BaseLLMClient,
    BatchResults,
    EmbedBatchResults,
    EmbedItem,
    PromptItem,
)
from context_use.store.sqlite import SqliteStore

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures/evals/longmemeval/sample.json"
)

_EMBEDDING_DIM = 768


class _FakeLLMClient(BaseLLMClient):
    """Stub LLM that returns deterministic answers and embeddings."""

    async def batch_submit(self, batch_id: str, prompts: list[PromptItem]) -> str:
        raise NotImplementedError

    async def batch_get_results(
        self, job_key: str, schema: type[BaseModel]
    ) -> BatchResults | None:  # type: ignore[type-arg]
        return None

    async def embed_batch_submit(self, batch_id: str, items: list[EmbedItem]) -> str:
        raise NotImplementedError

    async def embed_batch_get_results(self, job_key: str) -> EmbedBatchResults | None:
        return None

    async def completion(self, prompt: str) -> str:
        return "I don't know based on the available memories."

    async def structured_completion(
        self, prompt: PromptItem, schema: type[BaseModel]
    ) -> BaseModel:
        from evals.judge import _JudgeSchema

        return _JudgeSchema(reasoning="Stubbed.", verdict="CORRECT")

    async def embed_query(self, text: str) -> list[float]:
        return [0.1] * _EMBEDDING_DIM


@pytest.fixture
def dataset() -> LongMemEvalDataset:
    return LongMemEvalDataset.from_file(FIXTURE_PATH)


def _store_factory() -> SqliteStore:
    return SqliteStore(path=":memory:")


class TestLongMemEvalRunner:
    @pytest.mark.asyncio
    async def test_run_without_memory_generation(
        self, dataset: LongMemEvalDataset
    ) -> None:
        config = RunConfig(generate_memories=False, question_ids=["q001"])
        runner = LongMemEvalRunner(
            store_factory=_store_factory,
            llm_client=_FakeLLMClient(),
            config=config,
        )
        results = await runner.run(dataset)
        assert len(results) == 1
        assert results[0].question_id == "q001"
        assert results[0].question_type == "single-session-user"
        assert results[0].reference == "Python"
        assert results[0].hypothesis

    @pytest.mark.asyncio
    async def test_run_multiple_questions(self, dataset: LongMemEvalDataset) -> None:
        config = RunConfig(
            generate_memories=False,
            question_ids=["q001", "q003_abs"],
        )
        runner = LongMemEvalRunner(
            store_factory=_store_factory,
            llm_client=_FakeLLMClient(),
            config=config,
        )
        results = await runner.run(dataset)
        assert len(results) == 2
        ids = {r.question_id for r in results}
        assert ids == {"q001", "q003_abs"}

    @pytest.mark.asyncio
    async def test_run_and_judge(self, dataset: LongMemEvalDataset) -> None:
        config = RunConfig(
            generate_memories=False,
            question_ids=["q001"],
        )
        runner = LongMemEvalRunner(
            store_factory=_store_factory,
            llm_client=_FakeLLMClient(),
            config=config,
        )
        results, metrics = await runner.run_and_judge(dataset)
        assert len(results) == 1
        assert results[0].verdict is not None
        assert results[0].verdict.label == "CORRECT"
        assert metrics.total == 1
        assert metrics.accuracy == 1.0

    @pytest.mark.asyncio
    async def test_writes_output_file(
        self, dataset: LongMemEvalDataset, tmp_path: Path
    ) -> None:
        output = tmp_path / "results.jsonl"
        config = RunConfig(
            generate_memories=False,
            question_ids=["q001"],
            output_path=str(output),
        )
        runner = LongMemEvalRunner(
            store_factory=_store_factory,
            llm_client=_FakeLLMClient(),
            config=config,
        )
        await runner.run(dataset)
        assert output.exists()
        import json

        lines = output.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["question_id"] == "q001"
        assert "hypothesis" in data

    @pytest.mark.asyncio
    async def test_empty_question_ids_runs_all(
        self, dataset: LongMemEvalDataset
    ) -> None:
        config = RunConfig(generate_memories=False)
        runner = LongMemEvalRunner(
            store_factory=_store_factory,
            llm_client=_FakeLLMClient(),
            config=config,
        )
        results = await runner.run(dataset)
        assert len(results) == 4

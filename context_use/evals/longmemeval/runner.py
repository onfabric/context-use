from __future__ import annotations

import asyncio
import collections.abc
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from context_use.evals.judge import LLMJudge
from context_use.evals.longmemeval.ingest import question_to_thread_rows
from context_use.evals.longmemeval.schema import Question
from context_use.evals.metrics import compute_metrics
from context_use.evals.types import EvalMetrics, EvalResult

if TYPE_CHECKING:
    from context_use.evals.longmemeval.dataset import LongMemEvalDataset
    from context_use.llm.base import BaseLLMClient
    from context_use.store.base import Store

logger = logging.getLogger(__name__)


QA_PROMPT = """\
You are a helpful assistant answering questions based on your memories \
of past conversations with the user.

Here are the relevant memories:
{context}

Question (asked on {question_date}): {question}

Answer the question based on the memories above. If the memories do not \
contain enough information, say you don't know. Be concise."""


@dataclass
class RunConfig:
    """Controls how the evaluation pipeline runs."""

    top_k: int = 10
    generate_memories: bool = True
    output_path: str | None = None
    batch_advance_delay: float = 1.0
    question_ids: list[str] = field(default_factory=list)


class LongMemEvalRunner:
    """Orchestrates LongMemEval: ingest → (memories) → search → answer → judge.

    Each question is evaluated independently with a fresh store to ensure
    the haystack is isolated per question, matching the benchmark design.

    Usage::

        from context_use.store.sqlite import SqliteStore
        from context_use.llm.litellm import LiteLLMSyncClient

        runner = LongMemEvalRunner(
            store_factory=lambda: SqliteStore(path=":memory:"),
            llm_client=llm_client,
        )
        results = await runner.run(dataset)
    """

    def __init__(
        self,
        store_factory: StoreFactory,
        llm_client: BaseLLMClient,
        config: RunConfig | None = None,
    ) -> None:
        self._store_factory = store_factory
        self._llm_client = llm_client
        self._config = config or RunConfig()

    async def run(self, dataset: LongMemEvalDataset) -> list[EvalResult]:
        questions = dataset.questions
        if self._config.question_ids:
            allowed = set(self._config.question_ids)
            questions = [q for q in questions if q.question_id in allowed]

        results: list[EvalResult] = []
        for i, question in enumerate(questions):
            logger.info(
                "[%d/%d] %s (%s)",
                i + 1,
                len(questions),
                question.question_id,
                question.question_type,
            )
            try:
                result = await self._evaluate_question(question)
                results.append(result)
            except Exception:
                logger.error(
                    "Failed to evaluate %s", question.question_id, exc_info=True
                )

        if self._config.output_path:
            self._write_results(results)

        return results

    async def run_and_judge(
        self, dataset: LongMemEvalDataset
    ) -> tuple[list[EvalResult], EvalMetrics]:
        results = await self.run(dataset)
        judge = LLMJudge(self._llm_client)

        for result in results:
            try:
                verdict = await judge.judge(
                    question=dataset[result.question_id].question,
                    reference=result.reference,
                    hypothesis=result.hypothesis,
                )
                result.verdict = verdict
            except Exception:
                logger.error("Judge failed for %s", result.question_id, exc_info=True)

        metrics = compute_metrics(results)

        if self._config.output_path:
            self._write_results(results)

        return results, metrics

    async def _evaluate_question(self, question: Question) -> EvalResult:
        store = self._store_factory()
        try:
            await store.init()

            task_id = await self._create_eval_task(store, question)
            thread_rows = question_to_thread_rows(question)
            await store.insert_threads(thread_rows, task_id=task_id)

            if self._config.generate_memories:
                await self._generate_memories(store)

            hypothesis = await self._answer_question(store, question)

            return EvalResult(
                question_id=question.question_id,
                question_type=question.question_type,
                hypothesis=hypothesis,
                reference=question.answer,
            )
        finally:
            await store.close()

    @staticmethod
    async def _create_eval_task(store: Store, question: Question) -> str:
        from context_use.evals.longmemeval.ingest import INTERACTION_TYPE, PROVIDER
        from context_use.models.archive import Archive, ArchiveStatus
        from context_use.models.etl_task import EtlTask, EtlTaskStatus

        archive = Archive(provider=PROVIDER, status=ArchiveStatus.COMPLETED.value)
        archive = await store.create_archive(archive)
        task = EtlTask(
            archive_id=archive.id,
            provider=PROVIDER,
            interaction_type=INTERACTION_TYPE,
            source_uris=[f"eval:{question.question_id}"],
            status=EtlTaskStatus.COMPLETED.value,
        )
        task = await store.create_task(task)
        return task.id

    async def _generate_memories(self, store: Store) -> None:
        import context_use.memories.manager  # noqa: F401 — register managers
        from context_use.batch.grouper import CollectionGrouper, ThreadGroup
        from context_use.batch.manager import (
            BatchContext,
            get_manager_for_category,
        )
        from context_use.evals.longmemeval.ingest import INTERACTION_TYPE
        from context_use.memories.config import MemoryConfig
        from context_use.memories.factory import MemoryBatchFactory
        from context_use.memories.prompt.conversation import (
            ConversationMemoryPromptBuilder,
        )
        from context_use.models.batch import BatchCategory
        from context_use.storage.disk import DiskStorage

        threads = await store.get_unprocessed_threads(
            interaction_types=[INTERACTION_TYPE],
        )
        if not threads:
            return

        memory_config = MemoryConfig(
            prompt_builder=ConversationMemoryPromptBuilder,
            grouper=CollectionGrouper,
        )
        grouper = memory_config.create_grouper()
        groups: list[ThreadGroup] = grouper.group(threads)
        if not groups:
            return

        batches = await MemoryBatchFactory.create_batches(groups, store)
        ctx = BatchContext(
            store=store,
            llm_client=self._llm_client,
            storage=DiskStorage("/tmp/longmemeval-eval"),
        )

        for batch in batches:
            category = BatchCategory(batch.category)
            while True:
                manager_cls = get_manager_for_category(category)
                manager = manager_cls(batch=batch, ctx=ctx)
                instruction = await manager.try_advance_state()
                if instruction.stop:
                    break
                if instruction.countdown:
                    await asyncio.sleep(
                        min(instruction.countdown, self._config.batch_advance_delay)
                    )

                refreshed = await store.get_batch(batch.id)
                if refreshed is None:
                    break
                batch = refreshed

    async def _answer_question(
        self,
        store: Store,
        question: Question,
    ) -> str:
        from context_use.models.memory import MemoryStatus

        memories = await store.list_memories(
            status=MemoryStatus.active.value,
        )

        if memories:
            query_embedding = await self._llm_client.embed_query(question.question)
            search_results = await store.search_memories(
                query_embedding=query_embedding,
                top_k=self._config.top_k,
            )
            context = "\n".join(f"- {r.content}" for r in search_results)
        else:
            threads = await store.get_unprocessed_threads()
            context = "\n".join(
                t.get_message_content() or t.preview
                for t in threads[: self._config.top_k]
            )

        question_date = question.question_date or "unknown date"
        prompt = QA_PROMPT.format(
            context=context,
            question=question.question,
            question_date=question_date,
        )
        return await self._llm_client.completion(prompt)

    def _write_results(self, results: list[EvalResult]) -> None:
        path = Path(self._config.output_path)  # type: ignore[arg-type]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for r in results:
                line = {
                    "question_id": r.question_id,
                    "question_type": r.question_type,
                    "hypothesis": r.hypothesis,
                    "reference": r.reference,
                }
                if r.verdict:
                    line["verdict"] = r.verdict.label
                    line["reasoning"] = r.verdict.reasoning
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        logger.info("Results written to %s", path)


type StoreFactory = collections.abc.Callable[[], Store]

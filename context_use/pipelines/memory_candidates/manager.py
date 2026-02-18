"""Batch manager for the memory-candidates pipeline."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from context_use.batch.manager import BaseBatchManager, register_batch_manager
from context_use.batch.models import Batch, BatchCategory
from context_use.batch.states import (
    CompleteState,
    CreatedState,
    SkippedState,
    State,
)
from context_use.llm.base import BatchLLMClient, BatchResults
from context_use.models.memory import TapestryMemory
from context_use.models.thread import Thread
from context_use.pipelines.memory_candidates.extractor import MemoryCandidateExtractor
from context_use.pipelines.memory_candidates.factory import MemoryCandidateBatchFactory
from context_use.pipelines.memory_candidates.prompt import MemoryCandidateSchema
from context_use.pipelines.memory_candidates.states import (
    MemoryGenerateCompleteState,
    MemoryGeneratePendingState,
)

logger = logging.getLogger(__name__)


@register_batch_manager(BatchCategory.memory_candidates)
class MemoryCandidateBatchManager(BaseBatchManager):
    """Generates memory candidates from asset threads grouped by day.

    State machine:
        CREATED → MEMORY_GENERATE_PENDING → MEMORY_GENERATE_COMPLETE → COMPLETE
    """

    def __init__(
        self,
        batch: Batch,
        db: Session,
        llm_client: BatchLLMClient,
    ) -> None:
        super().__init__(batch, db)
        self.batch: Batch = batch
        self.extractor = MemoryCandidateExtractor(llm_client)
        self.batch_factory = MemoryCandidateBatchFactory

    def _get_batch_threads(self) -> list[Thread]:
        return self.batch_factory.get_batch_threads(self.batch, self.db)

    def _get_asset_threads(self) -> list[Thread]:
        return [t for t in self._get_batch_threads() if t.asset_uri is not None]

    async def _transition(self, current_state: State) -> State | None:
        match current_state:
            case CreatedState():
                logger.info("[%s] Starting memory-candidate generation", self.batch.id)
                return self._trigger_memory_generation()

            case MemoryGeneratePendingState() as state:
                logger.info("[%s] Polling memory generation", self.batch.id)
                return self._check_memory_generation_status(state)

            case MemoryGenerateCompleteState():
                logger.info("[%s] Memory generation complete", self.batch.id)
                return CompleteState()

            case _:
                raise ValueError(
                    f"Invalid state for memory-candidates batch: {current_state}"
                )

    def _trigger_memory_generation(self) -> State:
        threads = self._get_asset_threads()
        if not threads:
            return SkippedState(reason="No asset threads for memory generation")

        logger.info(
            "[%s] Submitting batch job for %d asset threads",
            self.batch.id,
            len(threads),
        )
        job_key = self.extractor.submit(self.batch.id, threads)
        return MemoryGeneratePendingState(job_key=job_key)

    def _check_memory_generation_status(
        self, state: MemoryGeneratePendingState
    ) -> State:
        results = self.extractor.get_results(state.job_key)

        if results is None:
            return state  # still polling

        count = self._store_memories(results)
        return MemoryGenerateCompleteState(memories_count=count)

    def _store_memories(
        self,
        results: BatchResults[MemoryCandidateSchema],
    ) -> int:
        """Write memory candidates to the ``tapestry_memories`` table."""
        threads = self._get_batch_threads()

        # Infer provider/interaction_type from the first thread
        first = threads[0] if threads else None
        provider = first.provider if first else "unknown"
        interaction_type = first.interaction_type if first else "unknown"

        count = 0
        for day_key, schema in results.items():
            memory_date = date.fromisoformat(day_key)

            for candidate in schema.candidates:
                memory = TapestryMemory(
                    batch_id=self.batch.id,
                    etl_task_id=self.batch.etl_task_id,
                    memory_date=memory_date,
                    content=candidate.content,
                    source_thread_ids=candidate.source_thread_ids,
                    provider=provider,
                    interaction_type=interaction_type,
                    tapestry_id=self.batch.tapestry_id,
                )
                self.db.add(memory)
                count += 1

        self.db.commit()
        logger.info("[%s] Stored %d memory candidates", self.batch.id, count)
        return count

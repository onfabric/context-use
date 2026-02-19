"""Batch manager for the memories pipeline."""

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
from context_use.etl.models.thread import Thread
from context_use.llm.base import BatchResults, EmbedBatchResults, EmbedItem, LLMClient
from context_use.memories.extractor import MemoryExtractor
from context_use.memories.factory import MemoryBatchFactory
from context_use.memories.models import TapestryMemory
from context_use.memories.prompt import MemorySchema
from context_use.memories.states import (
    MemoryEmbedCompleteState,
    MemoryEmbedPendingState,
    MemoryGenerateCompleteState,
    MemoryGeneratePendingState,
)
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


@register_batch_manager(BatchCategory.memories)
class MemoryBatchManager(BaseBatchManager):
    """Generates and embeds memories from asset threads grouped by day.

    State machine:
        CREATED → MEMORY_GENERATE_PENDING → MEMORY_GENERATE_COMPLETE
                → MEMORY_EMBED_PENDING → MEMORY_EMBED_COMPLETE → COMPLETE
    """

    def __init__(
        self,
        batch: Batch,
        db: Session,
        llm_client: LLMClient,
        storage: StorageBackend,
    ) -> None:
        super().__init__(batch, db)
        self.batch: Batch = batch
        self.llm_client = llm_client
        self.storage = storage
        self.extractor = MemoryExtractor(llm_client)
        self.batch_factory = MemoryBatchFactory

    def _get_batch_threads(self) -> list[Thread]:
        return self.batch_factory.get_batch_threads(self.batch, self.db)

    def _get_asset_threads(self) -> list[Thread]:
        threads = [t for t in self._get_batch_threads() if t.asset_uri is not None]
        for t in threads:
            if t.asset_uri:
                t.asset_uri = self.storage.resolve_local_path(t.asset_uri)
        return threads

    async def _transition(self, current_state: State) -> State | None:
        match current_state:
            case CreatedState():
                logger.info("[%s] Starting memory generation", self.batch.id)
                return await self._trigger_memory_generation()

            case MemoryGeneratePendingState() as state:
                logger.info("[%s] Polling memory generation", self.batch.id)
                return await self._check_memory_generation_status(state)

            case MemoryGenerateCompleteState():
                logger.info("[%s] Starting memory embedding", self.batch.id)
                return await self._trigger_embedding()

            case MemoryEmbedPendingState() as state:
                logger.info("[%s] Polling memory embedding", self.batch.id)
                return await self._check_embedding_status(state)

            case MemoryEmbedCompleteState():
                logger.info("[%s] Memory embedding complete", self.batch.id)
                return CompleteState()

            case _:
                raise ValueError(f"Invalid state for memories batch: {current_state}")

    async def _trigger_memory_generation(self) -> State:
        threads = self._get_asset_threads()
        if not threads:
            return SkippedState(reason="No asset threads for memory generation")

        logger.info(
            "[%s] Submitting batch job for %d asset threads",
            self.batch.id,
            len(threads),
        )
        job_key = await self.extractor.submit(self.batch.id, threads)
        return MemoryGeneratePendingState(job_key=job_key)

    async def _check_memory_generation_status(
        self, state: MemoryGeneratePendingState
    ) -> State:
        results = await self.extractor.get_results(state.job_key)

        if results is None:
            return state  # still polling

        count = self._store_memories(results)
        return MemoryGenerateCompleteState(memories_count=count)

    def _store_memories(
        self,
        results: BatchResults[MemorySchema],
    ) -> int:
        """Write memories to the ``tapestry_memories`` table."""
        count = 0
        for day_key, schema in results.items():
            memory_date = date.fromisoformat(day_key)

            for memory in schema.memories:
                row = TapestryMemory(
                    content=memory.content,
                    from_date=memory_date,
                    to_date=memory_date,
                    tapestry_id=self.batch.tapestry_id,
                )
                self.db.add(row)
                count += 1

        self.db.commit()
        logger.info("[%s] Stored %d memories", self.batch.id, count)
        return count

    def _get_unembedded_memories(self) -> list[TapestryMemory]:
        return (
            self.db.query(TapestryMemory)
            .filter(
                TapestryMemory.tapestry_id == self.batch.tapestry_id,
                TapestryMemory.embedding.is_(None),
            )
            .all()
        )

    async def _trigger_embedding(self) -> State:
        memories = self._get_unembedded_memories()
        if not memories:
            return MemoryEmbedCompleteState(embedded_count=0)

        items = [EmbedItem(item_id=m.id, text=m.content) for m in memories]

        logger.info(
            "[%s] Submitting embed batch for %d memories",
            self.batch.id,
            len(items),
        )
        job_key = await self.llm_client.embed_batch_submit(self.batch.id, items)
        return MemoryEmbedPendingState(job_key=job_key)

    async def _check_embedding_status(self, state: MemoryEmbedPendingState) -> State:
        results = await self.llm_client.embed_batch_get_results(state.job_key)

        if results is None:
            return state  # still polling

        count = self._store_embeddings(results)
        return MemoryEmbedCompleteState(embedded_count=count)

    def _store_embeddings(self, results: EmbedBatchResults) -> int:
        """Write embedding vectors back onto existing memory rows."""
        count = 0
        for memory_id, vector in results.items():
            memory = self.db.get(TapestryMemory, memory_id)
            if memory is None:
                logger.warning(
                    "[%s] Memory %s not found, skipping embedding",
                    self.batch.id,
                    memory_id,
                )
                continue
            memory.embedding = vector
            count += 1

        self.db.commit()
        logger.info("[%s] Stored %d embeddings", self.batch.id, count)
        return count

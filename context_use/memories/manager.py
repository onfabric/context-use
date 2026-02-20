from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_use.batch.manager import BaseBatchManager, register_batch_manager
from context_use.batch.models import Batch, BatchCategory
from context_use.batch.states import (
    CompleteState,
    CreatedState,
    SkippedState,
    State,
)
from context_use.llm.base import BatchResults, EmbedBatchResults, EmbedItem, LLMClient
from context_use.memories.extractor import MemoryExtractor
from context_use.memories.factory import MemoryBatchFactory
from context_use.memories.models import TapestryMemory
from context_use.memories.prompt import (
    GroupContext,
    MemorySchema,
)
from context_use.memories.states import (
    MemoryEmbedCompleteState,
    MemoryEmbedPendingState,
    MemoryGenerateCompleteState,
    MemoryGeneratePendingState,
)
from context_use.providers.registry import get_memory_config
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


@register_batch_manager(BatchCategory.memories)
class MemoryBatchManager(BaseBatchManager):
    """Generates and embeds memories from grouped threads.

    The prompt strategy is resolved automatically from the batch's
    interaction type.

    State machine:
        CREATED → MEMORY_GENERATE_PENDING → MEMORY_GENERATE_COMPLETE
                → MEMORY_EMBED_PENDING → MEMORY_EMBED_COMPLETE → COMPLETE
    """

    def __init__(
        self,
        batch: Batch,
        db: AsyncSession,
        llm_client: LLMClient,
        storage: StorageBackend,
    ) -> None:
        super().__init__(batch, db)
        self.batch: Batch = batch
        self.llm_client = llm_client
        self.storage = storage
        self.extractor = MemoryExtractor(llm_client)
        self.batch_factory = MemoryBatchFactory

    async def _get_group_contexts(self) -> list[GroupContext]:
        """Load groups from BatchThread and build GroupContexts."""
        groups = await self.batch_factory.get_batch_groups(self.batch, self.db)
        contexts: list[GroupContext] = []
        for group in groups:
            for t in group.threads:
                if t.asset_uri:
                    t.asset_uri = self.storage.resolve_local_path(t.asset_uri)
            contexts.append(
                GroupContext(
                    group_key=group.group_key,
                    new_threads=group.threads,
                )
            )
        return contexts

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
        contexts = await self._get_group_contexts()
        if not contexts:
            return SkippedState(reason="No groups for memory generation")

        all_threads = [t for ctx in contexts for t in ctx.new_threads]
        if not all_threads:
            return SkippedState(reason="No threads for memory generation")

        interaction_type = all_threads[0].interaction_type
        config = get_memory_config(interaction_type)
        builder = config.create_prompt_builder(contexts)

        if not builder.has_content():
            return SkippedState(reason="No processable content for memory generation")

        prompts = builder.build()
        if not prompts:
            return SkippedState(reason="Prompt builder produced no prompts")

        logger.info(
            "[%s] Submitting batch job for %d groups (%d prompts, %d total threads)",
            self.batch.id,
            len(contexts),
            len(prompts),
            len(all_threads),
        )
        job_key = await self.extractor.submit(self.batch.id, prompts)
        return MemoryGeneratePendingState(job_key=job_key)

    async def _check_memory_generation_status(
        self, state: MemoryGeneratePendingState
    ) -> State:
        results = await self.extractor.get_results(state.job_key)

        if results is None:
            return state  # still polling

        count = await self._store_memories(results)
        return MemoryGenerateCompleteState(memories_count=count)

    async def _store_memories(
        self,
        results: BatchResults[MemorySchema],
    ) -> int:
        """Write memories to the ``tapestry_memories`` table."""
        count = 0
        for group_key, schema in results.items():
            for memory in schema.memories:
                row = TapestryMemory(
                    content=memory.content,
                    from_date=date.fromisoformat(memory.from_date),
                    to_date=date.fromisoformat(memory.to_date),
                    tapestry_id=self.batch.tapestry_id,
                    group_key=group_key,
                )
                self.db.add(row)
                count += 1

        await self.db.commit()
        logger.info("[%s] Stored %d memories", self.batch.id, count)
        return count

    async def _get_unembedded_memories(self) -> list[TapestryMemory]:
        result = await self.db.execute(
            select(TapestryMemory).where(
                TapestryMemory.tapestry_id == self.batch.tapestry_id,
                TapestryMemory.embedding.is_(None),
            )
        )
        return list(result.scalars().all())

    async def _trigger_embedding(self) -> State:
        memories = await self._get_unembedded_memories()
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

        count = await self._store_embeddings(results)
        return MemoryEmbedCompleteState(embedded_count=count)

    async def _store_embeddings(self, results: EmbedBatchResults) -> int:
        """Write embedding vectors back onto existing memory rows."""
        count = 0
        for memory_id, vector in results.items():
            memory = await self.db.get(TapestryMemory, memory_id)
            if memory is None:
                logger.warning(
                    "[%s] Memory %s not found, skipping embedding",
                    self.batch.id,
                    memory_id,
                )
                continue
            memory.embedding = vector
            count += 1

        await self.db.commit()
        logger.info("[%s] Stored %d embeddings", self.batch.id, count)
        return count

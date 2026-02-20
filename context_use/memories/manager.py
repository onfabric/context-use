from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import select

from context_use.batch.manager import BaseBatchManager, register_batch_manager
from context_use.batch.models import Batch, BatchCategory
from context_use.batch.states import (
    CompleteState,
    CreatedState,
    SkippedState,
    State,
)
from context_use.llm.base import BatchResults, LLMClient
from context_use.memories.config import MemoryConfig
from context_use.memories.embedding import (
    store_memory_embeddings,
    submit_memory_embeddings,
)
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
from context_use.storage.base import StorageBackend

if TYPE_CHECKING:
    from context_use.db.base import DatabaseBackend

logger = logging.getLogger(__name__)


@register_batch_manager(BatchCategory.memories)
class MemoryBatchManager(BaseBatchManager):
    """Generates and embeds memories from grouped threads.

    The prompt strategy is resolved via an injected
    ``memory_config_resolver`` callable (interaction_type → MemoryConfig).

    State machine:
        CREATED → MEMORY_GENERATE_PENDING → MEMORY_GENERATE_COMPLETE
                → MEMORY_EMBED_PENDING → MEMORY_EMBED_COMPLETE → COMPLETE
    """

    def __init__(
        self,
        batch: Batch,
        db_backend: DatabaseBackend,
        llm_client: LLMClient,
        storage: StorageBackend,
        memory_config_resolver: Callable[[str], MemoryConfig],
    ) -> None:
        super().__init__(batch, db_backend)
        self.batch: Batch = batch
        self.llm_client = llm_client
        self.storage = storage
        self._memory_config_resolver = memory_config_resolver
        self.extractor = MemoryExtractor(llm_client)
        self.batch_factory = MemoryBatchFactory
        self._created_memory_ids: list[str] = []

    async def _get_group_contexts(self) -> list[GroupContext]:
        """Load groups from BatchThread and build GroupContexts."""
        assert self.db is not None
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
        config = self._memory_config_resolver(interaction_type)
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
        assert self.db is not None
        count = 0
        for group_key, schema in results.items():
            for memory in schema.memories:
                row = TapestryMemory(
                    content=memory.content,
                    from_date=date.fromisoformat(memory.from_date),
                    to_date=date.fromisoformat(memory.to_date),
                    group_key=group_key,
                )
                self.db.add(row)
                await self.db.flush()
                self._created_memory_ids.append(row.id)
                count += 1

        logger.info("[%s] Stored %d memories", self.batch.id, count)
        return count

    async def _get_batch_unembedded_memories(self) -> list[TapestryMemory]:
        """Return unembedded memories created by *this* batch only."""
        assert self.db is not None
        if not self._created_memory_ids:
            return []
        result = await self.db.execute(
            select(TapestryMemory).where(
                TapestryMemory.id.in_(self._created_memory_ids),
                TapestryMemory.embedding.is_(None),
            )
        )
        return list(result.scalars().all())

    async def _trigger_embedding(self) -> State:
        memories = await self._get_batch_unembedded_memories()
        if not memories:
            return MemoryEmbedCompleteState(embedded_count=0)

        job_key = await submit_memory_embeddings(
            memories, self.batch.id, self.llm_client
        )
        return MemoryEmbedPendingState(job_key=job_key)

    async def _check_embedding_status(self, state: MemoryEmbedPendingState) -> State:
        assert self.db is not None
        results = await self.llm_client.embed_batch_get_results(state.job_key)
        if results is None:
            return state

        count = await store_memory_embeddings(results, self.batch.id, self.db)
        return MemoryEmbedCompleteState(embedded_count=count)

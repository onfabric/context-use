from __future__ import annotations

import logging
from datetime import date

from context_use.batch.manager import (
    BaseBatchManager,
    BatchContext,
    register_batch_manager,
)
from context_use.batch.states import CompleteState, CreatedState, SkippedState, State
from context_use.facets.embedding import store_facet_embeddings, submit_facet_embeddings
from context_use.facets.linker import SemanticFacetLinker
from context_use.llm.base import BatchResults
from context_use.memories.embedding import (
    store_memory_embeddings,
    submit_memory_embeddings,
)
from context_use.memories.context import GroupContextBuilder
from context_use.memories.extractor import MemoryExtractor
from context_use.memories.factory import MemoryBatchFactory
from context_use.memories.prompt import GroupContext, MemorySchema
from context_use.memories.states import (
    FacetEmbedCompleteState,
    FacetEmbedPendingState,
    MemoryEmbedCompleteState,
    MemoryEmbedPendingState,
    MemoryGenerateCompleteState,
    MemoryGeneratePendingState,
)
from context_use.models.batch import Batch, BatchCategory
from context_use.models.facet import MemoryFacet
from context_use.models.memory import TapestryMemory

logger = logging.getLogger(__name__)


@register_batch_manager(BatchCategory.memories)
class MemoryBatchManager(BaseBatchManager):
    """Generates and embeds memories from grouped threads.

    The prompt strategy is resolved via the provider registry.

    State machine:
        CREATED → MEMORY_GENERATE_PENDING → MEMORY_GENERATE_COMPLETE
                → MEMORY_EMBED_PENDING → MEMORY_EMBED_COMPLETE → COMPLETE
    """

    def __init__(self, batch: Batch, ctx: BatchContext) -> None:
        super().__init__(batch, ctx)
        self.extractor = MemoryExtractor(ctx.llm_client)
        self.batch_factory = MemoryBatchFactory
        self.linker = SemanticFacetLinker(ctx.store)
        self._context_builder = GroupContextBuilder()

    async def _get_group_contexts(self) -> list[GroupContext]:
        """Load groups from BatchThread and build GroupContexts."""
        groups = await self.batch_factory.get_batch_groups(self.batch, self.ctx.store)
        return await self._context_builder.build_many(groups)

    async def _transition(self, current_state: State) -> State | None:
        match current_state:
            case CreatedState():
                logger.info("[%s] Starting memory generation", self.batch.id)
                return await self._trigger_memory_generation()

            case MemoryGeneratePendingState() as state:
                logger.info("[%s] Polling memory generation", self.batch.id)
                return await self._check_memory_generation_status(state)

            case MemoryGenerateCompleteState() as state:
                logger.info("[%s] Starting memory embedding", self.batch.id)
                return await self._trigger_embedding(state.created_memory_ids)

            case MemoryEmbedPendingState() as state:
                logger.info("[%s] Polling memory embedding", self.batch.id)
                return await self._check_embedding_status(state)

            case MemoryEmbedCompleteState():
                logger.info(
                    "[%s] Memory embedding complete — starting facet embedding",
                    self.batch.id,
                )
                return await self._trigger_facet_embedding()

            case FacetEmbedPendingState() as state:
                logger.info("[%s] Polling facet embedding", self.batch.id)
                return await self._check_facet_embedding_status(state)

            case FacetEmbedCompleteState():
                logger.info(
                    "[%s] Facet embedding complete — linking facets", self.batch.id
                )
                await self._link_facets()
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

        from context_use.providers.registry import get_memory_config

        prompts = []
        for ctx in contexts:
            it = ctx.new_threads[0].interaction_type
            config = get_memory_config(it)
            builder = config.create_prompt_builder(ctx)
            if builder.has_content():
                item = builder.build()
                if item is not None:
                    prompts.append(item)

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

        memory_ids = await self._store_memories(results)
        return MemoryGenerateCompleteState(
            memories_count=len(memory_ids),
            created_memory_ids=memory_ids,
        )

    async def _store_memories(
        self,
        results: BatchResults[MemorySchema],
    ) -> list[str]:
        """Write memories and their extracted facets via the Store.

        Returns the IDs of created memory rows so they can be persisted
        in the state object and survive process restarts.
        """
        memory_ids: list[str] = []
        facet_count = 0
        for group_id, schema in results.items():
            for memory in schema.memories:
                row = TapestryMemory(
                    content=memory.content,
                    from_date=date.fromisoformat(memory.from_date),
                    to_date=date.fromisoformat(memory.to_date),
                    group_id=group_id,
                )
                row = await self.ctx.store.create_memory(row)
                memory_ids.append(row.id)
                for f in memory.facets:
                    await self.ctx.store.create_memory_facet(
                        MemoryFacet(
                            memory_id=row.id,
                            batch_id=self.batch.id,
                            facet_type=f.facet_type,
                            facet_value=f.facet_value,
                        )
                    )
                    facet_count += 1

        logger.info(
            "[%s] Stored %d memories, %d facets",
            self.batch.id,
            len(memory_ids),
            facet_count,
        )
        return memory_ids

    async def _trigger_embedding(self, memory_ids: list[str]) -> State:
        memories = await self.ctx.store.get_unembedded_memories(memory_ids)
        if not memories:
            return MemoryEmbedCompleteState(embedded_count=0)

        job_key = await submit_memory_embeddings(
            memories, self.batch.id, self.ctx.llm_client
        )
        return MemoryEmbedPendingState(job_key=job_key)

    async def _check_embedding_status(self, state: MemoryEmbedPendingState) -> State:
        results = await self.ctx.llm_client.embed_batch_get_results(state.job_key)
        if results is None:
            return state

        count = await store_memory_embeddings(results, self.batch.id, self.ctx.store)
        return MemoryEmbedCompleteState(embedded_count=count)

    async def _trigger_facet_embedding(self) -> State:
        facets = await self.ctx.store.get_unembedded_memory_facets(
            batch_id=self.batch.id
        )
        if not facets:
            return FacetEmbedCompleteState(embedded_count=0)

        job_key = await submit_facet_embeddings(
            facets, self.batch.id, self.ctx.llm_client
        )
        return FacetEmbedPendingState(
            job_key=job_key,
            facet_ids=[f.id for f in facets],
        )

    async def _check_facet_embedding_status(
        self, state: FacetEmbedPendingState
    ) -> State:
        results = await self.ctx.llm_client.embed_batch_get_results(state.job_key)
        if results is None:
            return state

        count = await store_facet_embeddings(results, self.batch.id, self.ctx.store)
        return FacetEmbedCompleteState(embedded_count=count)

    async def _link_facets(self) -> None:
        unlinked = await self.ctx.store.get_unlinked_memory_facets()
        if not unlinked:
            return
        logger.info("[%s] Linking %d unlinked facets", self.batch.id, len(unlinked))
        await self.linker.link(unlinked)

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
from context_use.llm.base import LLMClient
from context_use.memories.embedding import (
    store_memory_embeddings,
    submit_memory_embeddings,
)
from context_use.memories.models import MemoryStatus, TapestryMemory
from context_use.memories.refinement.discovery import discover_refinement_clusters
from context_use.memories.refinement.prompt import (
    RefinementSchema,
    build_refinement_prompt,
)
from context_use.memories.refinement.states import (
    RefinementCompleteState,
    RefinementCreatedState,
    RefinementDiscoverState,
    RefinementEmbedCompleteState,
    RefinementEmbedPendingState,
    RefinementPendingState,
)

logger = logging.getLogger(__name__)


@register_batch_manager(BatchCategory.refinement)
class RefinementBatchManager(BaseBatchManager):
    """Discovers overlapping memories and refines them via LLM.

    State machine:
        CREATED -> REFINEMENT_DISCOVER (or SKIPPED)
                -> REFINEMENT_PENDING
                -> REFINEMENT_COMPLETE
                -> REFINEMENT_EMBED_PENDING
                -> REFINEMENT_EMBED_COMPLETE
                -> COMPLETE
    """

    def __init__(
        self,
        batch: Batch,
        db: AsyncSession,
        llm_client: LLMClient,
        **kwargs: object,
    ) -> None:
        super().__init__(batch, db)
        self.batch: Batch = batch
        self.llm_client = llm_client

    async def _transition(self, current_state: State) -> State | None:
        match current_state:
            case RefinementCreatedState() as state:
                logger.info("[%s] Starting refinement discovery", self.batch.id)
                return await self._discover(state.seed_memory_ids)

            case CreatedState():
                logger.info("[%s] Starting refinement (legacy)", self.batch.id)
                return await self._discover(self._get_seed_memory_ids_legacy())

            case RefinementDiscoverState() as state:
                logger.info("[%s] Submitting refinement prompts", self.batch.id)
                return await self._submit_refinement(state)

            case RefinementPendingState() as state:
                logger.info("[%s] Polling refinement results", self.batch.id)
                return await self._check_refinement_status(state)

            case RefinementCompleteState():
                logger.info("[%s] Starting refinement embedding", self.batch.id)
                return await self._trigger_embedding()

            case RefinementEmbedPendingState() as state:
                logger.info("[%s] Polling refinement embedding", self.batch.id)
                return await self._check_embedding_status(state)

            case RefinementEmbedCompleteState():
                logger.info("[%s] Refinement embedding complete", self.batch.id)
                return CompleteState()

            case _:
                raise ValueError(f"Invalid state for refinement batch: {current_state}")

    async def _discover(self, seed_ids: list[str]) -> State:
        if not seed_ids:
            return SkippedState(reason="No seed memory IDs for refinement")

        clusters = await discover_refinement_clusters(seed_ids, self.db)
        if not clusters:
            return SkippedState(reason="No refinement clusters found")

        logger.info(
            "[%s] Discovered %d clusters from %d seeds",
            self.batch.id,
            len(clusters),
            len(seed_ids),
        )
        return RefinementDiscoverState(
            clusters=clusters,
            cluster_count=len(clusters),
        )

    def _get_seed_memory_ids_legacy(self) -> list[str]:
        """Extract seed memory IDs from raw state dicts (pre-RefinementCreatedState)."""
        for state_dict in reversed(self.batch.states):
            seed_ids = state_dict.get("seed_memory_ids")
            if seed_ids:
                return seed_ids
        return []

    async def _submit_refinement(self, state: RefinementDiscoverState) -> State:
        prompts = []
        for idx, cluster_ids in enumerate(state.clusters):
            result = await self.db.execute(
                select(TapestryMemory).where(TapestryMemory.id.in_(cluster_ids))
            )
            memories = list(result.scalars().all())
            if len(memories) < 2:
                continue

            prompt = build_refinement_prompt(
                cluster_id=f"cluster-{idx}",
                memories=memories,
            )
            prompts.append(prompt)

        if not prompts:
            return SkippedState(reason="No valid clusters after loading memories")

        logger.info(
            "[%s] Submitting %d refinement prompts", self.batch.id, len(prompts)
        )
        job_key = await self.llm_client.batch_submit(self.batch.id, prompts)
        return RefinementPendingState(job_key=job_key)

    async def _check_refinement_status(self, state: RefinementPendingState) -> State:
        results = await self.llm_client.batch_get_results(
            state.job_key, RefinementSchema
        )
        if results is None:
            return state  # still polling

        refined_count, superseded_count = await self._store_refinement_results(results)
        return RefinementCompleteState(
            refined_count=refined_count,
            superseded_count=superseded_count,
        )

    async def _store_refinement_results(
        self,
        results: dict[str, RefinementSchema],
    ) -> tuple[int, int]:
        """Create refined memories and supersede consumed inputs."""
        refined_count = 0
        superseded_count = 0
        all_superseded_ids: set[str] = set()

        for _cluster_id, schema in results.items():
            for refined in schema.memories:
                new_memory = TapestryMemory(
                    content=refined.content,
                    from_date=date.fromisoformat(refined.from_date),
                    to_date=date.fromisoformat(refined.to_date),
                    status=MemoryStatus.active.value,
                    source_memory_ids=refined.source_ids,
                )
                self.db.add(new_memory)
                await self.db.flush()
                refined_count += 1

                for source_id in refined.source_ids:
                    if source_id in all_superseded_ids:
                        continue
                    source = await self.db.get(TapestryMemory, source_id)
                    if source and source.status == MemoryStatus.active.value:
                        source.status = MemoryStatus.superseded.value
                        source.superseded_by = new_memory.id
                        all_superseded_ids.add(source_id)
                        superseded_count += 1

        await self.db.commit()
        logger.info(
            "[%s] Stored %d refined memories, superseded %d",
            self.batch.id,
            refined_count,
            superseded_count,
        )
        return refined_count, superseded_count

    async def _get_unembedded_refined_memories(self) -> list[TapestryMemory]:
        result = await self.db.execute(
            select(TapestryMemory).where(
                TapestryMemory.status == MemoryStatus.active.value,
                TapestryMemory.source_memory_ids.isnot(None),
                TapestryMemory.embedding.is_(None),
            )
        )
        return list(result.scalars().all())

    async def _trigger_embedding(self) -> State:
        memories = await self._get_unembedded_refined_memories()
        if not memories:
            return RefinementEmbedCompleteState(embedded_count=0)

        job_key = await submit_memory_embeddings(
            memories, self.batch.id, self.llm_client
        )
        return RefinementEmbedPendingState(job_key=job_key)

    async def _check_embedding_status(
        self, state: RefinementEmbedPendingState
    ) -> State:
        results = await self.llm_client.embed_batch_get_results(state.job_key)
        if results is None:
            return state

        count = await store_memory_embeddings(results, self.batch.id, self.db)
        return RefinementEmbedCompleteState(embedded_count=count)

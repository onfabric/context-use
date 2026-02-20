from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_use.batch.models import Batch, BatchCategory
from context_use.memories.models import MemoryStatus, TapestryMemory
from context_use.memories.refinement.states import RefinementCreatedState

logger = logging.getLogger(__name__)


class RefinementBatchFactory:
    """Creates a refinement batch from all active, embedded, un-refined memories."""

    @classmethod
    async def create_refinement_batches(
        cls,
        db: AsyncSession,
    ) -> list[Batch]:
        stmt = select(TapestryMemory.id).where(
            TapestryMemory.status == MemoryStatus.active.value,
            TapestryMemory.embedding.isnot(None),
            TapestryMemory.source_memory_ids.is_(None),
        )
        result = await db.execute(stmt)
        seed_ids = [row[0] for row in result.all()]

        if not seed_ids:
            logger.info("No seed memories for refinement")
            return []

        initial_state = RefinementCreatedState(seed_memory_ids=seed_ids)

        batch = Batch(
            batch_number=1,
            category=BatchCategory.refinement.value,
            states=[initial_state.model_dump(mode="json")],
        )
        db.add(batch)
        await db.flush()

        logger.info(
            "Created refinement batch %s (%d seed memories)",
            batch.id,
            len(seed_ids),
        )
        return [batch]

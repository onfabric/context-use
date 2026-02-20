from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_use.batch.models import Batch, BatchCategory
from context_use.memories.models import MemoryStatus, TapestryMemory
from context_use.memories.refinement.states import RefinementCreatedState

logger = logging.getLogger(__name__)


class RefinementBatchFactory:
    """Creates refinement batches from completed memory batches.

    Queries the memories produced by the completed memory batches,
    encodes their IDs as ``seed_memory_ids`` in the initial state,
    and creates one refinement Batch per ETL task.
    """

    @classmethod
    async def create_from_memory_batches(
        cls,
        completed_batches: list[Batch],
        db: AsyncSession,
    ) -> list[Batch]:
        memory_batches = [
            b
            for b in completed_batches
            if b.category == BatchCategory.memories.value
            and b.current_status == "COMPLETE"
        ]

        if not memory_batches:
            return []

        # Group by ETL task so we create one refinement batch per task
        by_task: dict[str, list[Batch]] = {}
        for b in memory_batches:
            by_task.setdefault(b.etl_task_id, []).append(b)

        refinement_batches: list[Batch] = []

        for etl_task_id, batches in by_task.items():
            stmt = select(TapestryMemory.id).where(
                TapestryMemory.status == MemoryStatus.active.value,
                TapestryMemory.embedding.isnot(None),
                TapestryMemory.source_memory_ids.is_(None),
            )
            result = await db.execute(stmt)
            seed_ids = [row[0] for row in result.all()]

            if not seed_ids:
                logger.info("[%s] No seed memories for refinement", etl_task_id)
                continue

            initial_state = RefinementCreatedState(seed_memory_ids=seed_ids)

            batch = Batch(
                etl_task_id=etl_task_id,
                batch_number=1,
                category=BatchCategory.refinement.value,
                states=[initial_state.model_dump(mode="json")],
            )
            db.add(batch)
            await db.flush()

            logger.info(
                "Created refinement batch %s for ETL task %s (%d seed memories)",
                batch.id,
                etl_task_id,
                len(seed_ids),
            )
            refinement_batches.append(batch)

        if refinement_batches:
            await db.commit()

        return refinement_batches

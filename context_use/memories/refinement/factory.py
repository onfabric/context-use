from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from context_use.memories.refinement.states import RefinementCreatedState
from context_use.models.batch import Batch, BatchCategory

if TYPE_CHECKING:
    from context_use.store.base import Store

logger = logging.getLogger(__name__)


class RefinementBatchFactory:
    """Creates a refinement batch from all active, embedded, un-refined memories."""

    @classmethod
    async def create_refinement_batches(
        cls,
        store: Store,
    ) -> list[Batch]:
        seed_ids = await store.get_refinable_memory_ids()

        if not seed_ids:
            logger.info("No seed memories for refinement")
            return []

        initial_state = RefinementCreatedState(seed_memory_ids=seed_ids)

        batch = Batch(
            batch_number=1,
            category=BatchCategory.refinement.value,
            states=[initial_state.model_dump(mode="json")],
        )
        batch = await store.create_batch(batch, [])

        logger.info(
            "Created refinement batch %s (%d seed memories)",
            batch.id,
            len(seed_ids),
        )
        return [batch]

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from context_use.batch.grouper import ThreadGroup
from context_use.models.batch import Batch, BatchCategory

if TYPE_CHECKING:
    from context_use.store.base import Store

logger = logging.getLogger(__name__)


class BaseBatchFactory:
    """Creates batches from pre-grouped threads.

    Sub-classes define:
    * ``BATCH_CATEGORIES`` — which categories to create batches for
    """

    BATCH_CATEGORIES: ClassVar[list[BatchCategory]]

    MAX_GROUPS_PER_BATCH = 50

    @classmethod
    async def get_batch_groups(
        cls,
        batch: Batch,
        store: Store,
    ) -> list[ThreadGroup]:
        """Return threads for *batch*, organised by group_id."""
        return await store.get_batch_groups(batch.id)

    @classmethod
    def _bin_pack_groups(
        cls,
        groups: list[ThreadGroup],
    ) -> list[list[ThreadGroup]]:
        """Split *groups* into chunks of at most MAX_GROUPS_PER_BATCH."""
        batches: list[list[ThreadGroup]] = []
        for i in range(0, len(groups), cls.MAX_GROUPS_PER_BATCH):
            batches.append(groups[i : i + cls.MAX_GROUPS_PER_BATCH])
        return batches

    @classmethod
    async def create_batches(
        cls,
        groups: list[ThreadGroup],
        store: Store,
    ) -> list[Batch]:
        """Bin-pack *groups* into batches and persist them.

        Each group's threads are recorded via the Store so the manager
        can retrieve them later.  Groups from different interaction
        types can coexist in the same batch.
        """
        if not groups:
            return []

        from context_use.batch.states import CreatedState

        packed = cls._bin_pack_groups(groups)
        thread_count = sum(len(g.threads) for g in groups)

        logger.info(
            "Creating %d batch(es) × %d categories (%d threads, %d groups)",
            len(packed),
            len(cls.BATCH_CATEGORIES),
            thread_count,
            len(groups),
        )

        batch_models: list[Batch] = []
        for batch_num, group_list in enumerate(packed, 1):
            for category in cls.BATCH_CATEGORIES:
                batch = Batch(
                    batch_number=batch_num,
                    category=category.value,
                    states=[CreatedState().model_dump(mode="json")],
                )
                batch = await store.create_batch(batch, group_list)
                batch_models.append(batch)

        return batch_models

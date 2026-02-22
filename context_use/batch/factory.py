from __future__ import annotations

import logging
from collections import defaultdict
from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_use.batch.grouper import ThreadGroup
from context_use.batch.models import Batch, BatchCategory, BatchThread
from context_use.etl.models.thread import Thread

logger = logging.getLogger(__name__)


class BaseBatchFactory:
    """Creates batches from pre-grouped threads.

    Sub-classes define:
    * ``BATCH_CATEGORIES`` — which categories to create batches for
    """

    BATCH_CATEGORIES: ClassVar[list[BatchCategory]]

    MAX_GROUPS_PER_BATCH = 50

    @classmethod
    async def get_batch_threads(cls, batch: Batch, db: AsyncSession) -> list[Thread]:
        """Get all threads assigned to *batch* via the BatchThread table."""
        stmt = (
            select(Thread)
            .join(BatchThread, BatchThread.thread_id == Thread.id)
            .where(BatchThread.batch_id == batch.id)
            .order_by(Thread.asat)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def get_batch_groups(
        cls,
        batch: Batch,
        db: AsyncSession,
    ) -> list[ThreadGroup]:
        """Return threads for *batch*, organised by group_key."""
        stmt = (
            select(BatchThread.group_key, Thread)
            .join(Thread, BatchThread.thread_id == Thread.id)
            .where(BatchThread.batch_id == batch.id)
            .order_by(BatchThread.group_key, Thread.asat)
        )
        rows = (await db.execute(stmt)).all()

        groups_map: dict[str, list[Thread]] = defaultdict(list)
        for group_key, thread in rows:
            groups_map[group_key].append(thread)

        return [ThreadGroup(group_key=k, threads=v) for k, v in groups_map.items()]

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
        db: AsyncSession,
    ) -> list[Batch]:
        """Bin-pack *groups* into batches and persist them.

        Each group's threads are recorded in the ``BatchThread`` join
        table so the manager can retrieve them later.  Groups from
        different interaction types can coexist in the same batch.
        """
        if not groups:
            return []

        packed = cls._bin_pack_groups(groups)
        thread_count = sum(len(t) for g in groups for t in [g.threads])

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
                )
                db.add(batch)
                await db.flush()

                for grp in group_list:
                    for thread in grp.threads:
                        db.add(
                            BatchThread(
                                batch_id=batch.id,
                                thread_id=thread.id,
                                group_key=grp.group_key,
                            )
                        )

                batch_models.append(batch)

        await db.flush()
        return batch_models

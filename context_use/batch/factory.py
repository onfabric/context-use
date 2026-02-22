from __future__ import annotations

import logging
from abc import ABC
from collections import defaultdict
from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_use.batch.grouper import ThreadGroup, ThreadGrouper
from context_use.batch.models import Batch, BatchCategory, BatchThread
from context_use.etl.models.etl_task import EtlTask
from context_use.etl.models.thread import Thread

logger = logging.getLogger(__name__)


class BaseBatchFactory(ABC):
    """Creates batches from ETL task threads using a ThreadGrouper.

    Sub-classes define:
    * ``BATCH_CATEGORIES`` — which categories to create batches for
    * ``cutoff_days``      — optional age filter for threads
    """

    BATCH_CATEGORIES: ClassVar[list[BatchCategory]]

    cutoff_days: ClassVar[float | None]
    """Threads older than this many days are excluded. ``None`` = no cutoff."""

    MAX_GROUPS_PER_BATCH = 50

    @classmethod
    def _get_batch_eligible_threads_stmt(
        cls,
        etl_task_id: str,
    ):
        """Select statement for threads eligible for batching."""
        from datetime import UTC, datetime, timedelta

        stmt = select(Thread).where(Thread.etl_task_id == etl_task_id)

        if cls.cutoff_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=cls.cutoff_days)
            stmt = stmt.where(Thread.asat >= cutoff)

        return stmt.order_by(Thread.asat, Thread.id)

    @classmethod
    async def _load_eligible_threads(
        cls,
        etl_task_id: str,
        db: AsyncSession,
    ) -> list[Thread]:
        stmt = cls._get_batch_eligible_threads_stmt(etl_task_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

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
    async def _create_batches(
        cls,
        etl_task_id: str,
        db: AsyncSession,
        grouper: ThreadGrouper,
    ) -> list[Batch]:
        etl_task_result = await db.execute(
            select(EtlTask).where(EtlTask.id == etl_task_id)
        )
        etl_task = etl_task_result.scalars().first()
        if not etl_task:
            logger.error("ETL task %s not found", etl_task_id)
            return []

        if etl_task.uploaded_count == 0:
            logger.info(
                "Skipping batch creation — 0 uploaded threads for %s", etl_task_id
            )
            return []

        threads = await cls._load_eligible_threads(etl_task_id, db)
        if not threads:
            logger.info("[%s] No eligible threads for batching", etl_task_id)
            return []

        groups = grouper.group(threads)
        if not groups:
            logger.info("[%s] Grouper produced no groups", etl_task_id)
            return []

        packed = cls._bin_pack_groups(groups)

        logger.info(
            "Creating %d batch(es) × %d categories for ETL task %s "
            "(%d threads, %d groups)",
            len(packed),
            len(cls.BATCH_CATEGORIES),
            etl_task_id,
            len(threads),
            len(groups),
        )

        batch_models: list[Batch] = []
        for batch_num, group_list in enumerate(packed, 1):
            for category in cls.BATCH_CATEGORIES:
                batch = Batch(
                    etl_task_id=etl_task_id,
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

    @classmethod
    async def create_batches(
        cls,
        etl_task_id: str,
        db: AsyncSession,
        grouper: ThreadGrouper,
    ) -> list[Batch]:
        """Public entry point: group threads, bin-pack, and create batches.

        Returns the list of Batch rows (already committed).
        """
        return await cls._create_batches(
            etl_task_id=etl_task_id,
            db=db,
            grouper=grouper,
        )

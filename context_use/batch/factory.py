from __future__ import annotations

import logging
from abc import ABC
from typing import ClassVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from context_use.batch.models import Batch, BatchCategory
from context_use.etl.models.etl_task import EtlTask
from context_use.etl.models.thread import Thread

logger = logging.getLogger(__name__)


class BaseBatchFactory(ABC):
    """Creates batches from ETL task threads and dispatches processing.

    Sub-classes define:
    * ``BATCH_CATEGORIES`` — which categories to create batches for
    * ``cutoff_days``      — optional age filter for threads
    """

    BATCH_CATEGORIES: ClassVar[list[BatchCategory]]
    """Which categories to create batches for."""

    cutoff_days: ClassVar[float | None]
    """Threads older than this many days are excluded. ``None`` = no cutoff."""

    MAX_THREADS_PER_BATCH = 1000
    BATCH_COUNTDOWN_INTERVAL_SECS = 5

    @classmethod
    def _get_batch_eligible_threads_stmt(
        cls,
        etl_task_id: str,
    ):
        """Base select statement for threads eligible for batching.

        Ordered by ``(asat, id)`` for deterministic OFFSET/LIMIT assignment.
        """
        from datetime import UTC, datetime, timedelta

        stmt = select(Thread).where(Thread.etl_task_id == etl_task_id)

        if cls.cutoff_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=cls.cutoff_days)
            stmt = stmt.where(Thread.asat >= cutoff)

        return stmt.order_by(Thread.asat, Thread.id)

    @classmethod
    async def get_batch_threads(cls, batch: Batch, db: AsyncSession) -> list[Thread]:
        """Get threads for a specific batch via OFFSET/LIMIT."""
        offset = (batch.batch_number - 1) * cls.MAX_THREADS_PER_BATCH
        stmt = (
            cls._get_batch_eligible_threads_stmt(batch.etl_task_id)
            .offset(offset)
            .limit(cls.MAX_THREADS_PER_BATCH)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def _create_batches(
        cls,
        etl_task_id: str,
        db: AsyncSession,
        tapestry_id: str | None = None,
    ) -> list[Batch]:
        """Create Batch rows for each category, splitting by MAX_THREADS_PER_BATCH."""
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

        count_stmt = select(func.count()).select_from(
            cls._get_batch_eligible_threads_stmt(etl_task_id).subquery()
        )
        total_result = await db.execute(count_stmt)
        total = total_result.scalar_one()
        if total == 0:
            logger.info("[%s] No eligible threads for batching", etl_task_id)
            return []

        chunk = cls.MAX_THREADS_PER_BATCH
        num_batches = (total + chunk - 1) // chunk

        logger.info(
            "Creating %d batch(es) × %d categories for ETL task %s (%d threads)",
            num_batches,
            len(cls.BATCH_CATEGORIES),
            etl_task_id,
            total,
        )

        batch_models: list[Batch] = []
        for batch_num in range(1, num_batches + 1):
            for category in cls.BATCH_CATEGORIES:
                batch_model = Batch(
                    etl_task_id=etl_task_id,
                    batch_number=batch_num,
                    category=category.value,
                    tapestry_id=tapestry_id,
                )
                db.add(batch_model)
                batch_models.append(batch_model)

        await db.commit()
        return batch_models

    @classmethod
    async def create_batches(
        cls,
        etl_task_id: str,
        db: AsyncSession,
        tapestry_id: str | None = None,
    ) -> list[Batch]:
        """Public entry point: create batches for an ETL task.

        Returns the list of Batch rows (already committed).
        The caller (runner) is responsible for dispatching them.
        """
        return await cls._create_batches(
            etl_task_id=etl_task_id,
            db=db,
            tapestry_id=tapestry_id,
        )

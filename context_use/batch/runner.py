from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from context_use.batch.manager import (
    BaseBatchManager,
    ScheduleInstruction,
    get_manager_for_category,
)
from context_use.batch.models import Batch, BatchCategory

logger = logging.getLogger(__name__)


async def run_batch(manager: BaseBatchManager) -> None:
    """Drive a single batch to completion using an async loop.

    Equivalent for Celery orchestration:

        @celery.task
        def try_advance_batch_task(self, batch_id):
            instruction = run_async(manager.try_advance_state())
            if not instruction.stop:
                try_advance_batch_task.apply_async(
                    (batch_id,), countdown=instruction.countdown or 0
                )
    """
    while True:
        instruction: ScheduleInstruction = await manager.try_advance_state()

        if instruction.stop:
            return

        if instruction.countdown:
            await asyncio.sleep(instruction.countdown)


async def run_batches(
    batches: list[Batch],
    db: AsyncSession,
    *,
    manager_kwargs: dict | None = None,
) -> None:
    """Run multiple batches concurrently.

    Each batch gets its own ``BaseBatchManager`` (resolved via the category
    registry) and is driven by ``run_batch``.
    """
    manager_kwargs = manager_kwargs or {}

    tasks = []
    for batch in batches:
        category = BatchCategory(batch.category)
        manager_cls = get_manager_for_category(category)
        manager = manager_cls(batch=batch, db=db, **manager_kwargs)
        tasks.append(asyncio.create_task(run_batch(manager)))

    if tasks:
        await asyncio.gather(*tasks)

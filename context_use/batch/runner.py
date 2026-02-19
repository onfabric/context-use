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
from context_use.batch.policy import ImmediateRunPolicy, RunPolicy

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


async def run_pipeline(
    batches: list[Batch],
    db: AsyncSession,
    *,
    policy: RunPolicy | None = None,
    manager_kwargs: dict | None = None,
) -> None:
    """Top-level entry point: check policy then process batches.

    ``policy`` defaults to ``ImmediateRunPolicy`` (always allows, no
    tracking).  Hosted deployments can supply a ``ManagedRunPolicy``
    that enforces mutual exclusion and records pipeline runs.
    """
    policy = policy or ImmediateRunPolicy()

    run_id = await policy.acquire()
    if run_id is None:
        logger.info("Pipeline run rejected by policy — skipping")
        return

    try:
        await run_batches(batches, db=db, manager_kwargs=manager_kwargs)
    except Exception:
        await policy.release(run_id, success=False)
        raise
    else:
        await policy.release(run_id, success=True)

from __future__ import annotations

import asyncio
import logging

from context_use.batch.manager import (
    BaseBatchManager,
    BatchContext,
    ScheduleInstruction,
    get_manager_for_category,
)
from context_use.batch.policy import ImmediateRunPolicy, RunPolicy
from context_use.models.batch import Batch, BatchCategory

logger = logging.getLogger(__name__)


async def run_batch(manager: BaseBatchManager) -> None:
    """Drive a single batch to completion using an async loop."""
    while True:
        instruction: ScheduleInstruction = await manager.try_advance_state()

        if instruction.stop:
            return

        if instruction.countdown:
            await asyncio.sleep(instruction.countdown)


async def run_batches(
    batches: list[Batch],
    ctx: BatchContext,
) -> None:
    """Run multiple batches concurrently.

    Each batch gets its own ``BaseBatchManager`` (resolved via the category
    registry).  All managers share the ``ctx`` instance.
    """
    tasks = []
    for batch in batches:
        category = BatchCategory(batch.category)
        manager_cls = get_manager_for_category(category)
        manager = manager_cls(batch=batch, ctx=ctx)
        tasks.append(asyncio.create_task(run_batch(manager)))

    if tasks:
        await asyncio.gather(*tasks)


async def run_pipeline(
    batches: list[Batch],
    ctx: BatchContext,
    *,
    policy: RunPolicy | None = None,
) -> None:
    """Top-level entry point: check policy then process batches."""
    policy = policy or ImmediateRunPolicy()

    run_id = await policy.acquire()
    if run_id is None:
        logger.info("Pipeline run rejected by policy — skipping")
        return

    try:
        await run_batches(batches, ctx=ctx)
    except Exception:
        await policy.release(run_id, success=False)
        raise
    else:
        await policy.release(run_id, success=True)

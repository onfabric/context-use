"""Shared embedding helpers for batch managers that embed TapestryMemory rows."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from context_use.llm.base import BaseLLMClient, EmbedBatchResults, EmbedItem
from context_use.models.memory import TapestryMemory

if TYPE_CHECKING:
    from context_use.store.base import Store

logger = logging.getLogger(__name__)


async def submit_memory_embeddings(
    memories: list[TapestryMemory],
    batch_id: str,
    llm_client: BaseLLMClient,
) -> str:
    """Submit an embedding batch job for *memories*. Returns the job key."""
    items = [EmbedItem(item_id=m.id, text=m.content) for m in memories]
    logger.info("[%s] Submitting embed batch for %d memories", batch_id, len(items))
    return await llm_client.embed_batch_submit(batch_id, items)


async def store_memory_embeddings(
    results: EmbedBatchResults,
    batch_id: str,
    store: Store,
) -> int:
    """Write embedding vectors back onto existing memory rows.

    Returns count stored.
    """
    memory_ids = list(results.keys())
    memories = await store.get_memories(memory_ids)
    memories_by_id = {m.id: m for m in memories}

    count = 0
    for memory_id, vector in results.items():
        memory = memories_by_id.get(memory_id)
        if memory is None:
            logger.warning(
                "[%s] Memory %s not found, skipping embedding",
                batch_id,
                memory_id,
            )
            continue
        memory.embedding = vector
        await store.update_memory(memory)
        count += 1

    logger.info("[%s] Stored %d embeddings", batch_id, count)
    return count

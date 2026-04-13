from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from context_use.llm.base import BaseLLMClient, EmbedBatchResults, EmbedItem
from context_use.models.thread import Thread

if TYPE_CHECKING:
    from context_use.store.base import Store

logger = logging.getLogger(__name__)


async def submit_thread_embeddings(
    threads: list[Thread],
    batch_id: str,
    llm_client: BaseLLMClient,
) -> str:
    items = [
        EmbedItem(item_id=t.id, text=text)
        for t in threads
        if (text := t.get_embeddable_content()) is not None
    ]
    if not items:
        raise ValueError("No threads with embeddable content")
    logger.info("[%s] Submitting embed batch for %d threads", batch_id, len(items))
    return await llm_client.embed_batch_submit(batch_id, items)


async def store_thread_embeddings(
    results: EmbedBatchResults,
    batch_id: str,
    store: Store,
) -> int:
    count = 0
    for thread_id, vector in results.items():
        await store.upsert_thread_embedding(thread_id, vector)
        count += 1
    logger.info("[%s] Stored %d thread embeddings", batch_id, count)
    return count

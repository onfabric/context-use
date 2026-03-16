from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from context_use.llm.base import BaseLLMClient, EmbedBatchResults, EmbedItem
from context_use.models.facet import MemoryFacet

if TYPE_CHECKING:
    from context_use.store.base import Store

logger = logging.getLogger(__name__)


async def submit_facet_embeddings(
    facets: list[MemoryFacet],
    batch_id: str,
    llm_client: BaseLLMClient,
) -> str:
    """Submit an embedding batch job for *facets*. Returns the job key."""
    items = [EmbedItem(item_id=f.id, text=f.facet_value) for f in facets]
    logger.info("[%s] Submitting embed batch for %d facets", batch_id, len(items))
    return await llm_client.embed_batch_submit(batch_id, items)


async def store_facet_embeddings(
    results: EmbedBatchResults,
    batch_id: str,
    store: Store,
) -> int:
    """Write embedding vectors into ``vec_facets`` for each result.

    Returns count stored.
    """
    count = 0
    for facet_id, vector in results.items():
        await store.create_facet_embedding(facet_id, vector)
        count += 1

    logger.info("[%s] Stored %d facet embeddings", batch_id, count)
    return count

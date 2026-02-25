from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from context_use.models.memory import EMBEDDING_DIMENSIONS
from context_use.store.base import MemorySearchResult

if TYPE_CHECKING:
    from context_use.llm.base import BaseLLMClient
    from context_use.store.base import Store


async def search_memories(
    store: Store,
    *,
    query: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    top_k: int = 5,
    llm_client: BaseLLMClient,
) -> list[MemorySearchResult]:
    """Search memories by semantic similarity, time range, or both.

    This is a thin adapter that embeds the query (if provided) and
    delegates to ``store.search_memories()``.
    """
    if query is None and from_date is None and to_date is None:
        raise ValueError("Provide at least one of: query, from_date, to_date")

    query_embedding: list[float] | None = None
    if query is not None:
        query_embedding = await llm_client.embed_query(query)
        assert len(query_embedding) == EMBEDDING_DIMENSIONS

    return await store.search_memories(
        query_embedding=query_embedding,
        from_date=from_date,
        to_date=to_date,
        top_k=top_k,
    )

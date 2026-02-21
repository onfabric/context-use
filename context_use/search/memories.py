from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from context_use.memories.models import (
    EMBEDDING_DIMENSIONS,
    MemoryStatus,
    TapestryMemory,
)

if TYPE_CHECKING:
    from context_use.llm.base import LLMClient


@dataclass(frozen=True)
class MemorySearchResult:
    id: str
    content: str
    from_date: date
    to_date: date
    similarity: float | None


async def search_memories(
    session: AsyncSession,
    *,
    query: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    top_k: int = 5,
    llm_client: LLMClient | None = None,
) -> list[MemorySearchResult]:
    """Search memories by semantic similarity, time range, or both.

    Args:
        session: Active async database session.
        query: Free-text query for semantic search (requires ``llm_client``).
        from_date: Only include memories whose ``from_date >= from_date``.
        to_date: Only include memories whose ``to_date <= to_date``.
        top_k: Maximum number of results to return.
        llm_client: Required when *query* is provided. Ensures the same
            embedding model is used for queries and stored vectors.

    Returns:
        A list of :class:`MemorySearchResult` ordered by relevance (semantic)
        or date (time-range only).
    """
    if query is None and from_date is None and to_date is None:
        raise ValueError("Provide at least one of: query, from_date, to_date")

    query_vec: list[float] | None = None
    if query is not None:
        if llm_client is None:
            raise ValueError("llm_client is required for semantic search")
        query_vec = await llm_client.embed_query(query)
        assert len(query_vec) == EMBEDDING_DIMENSIONS

    columns: list = [TapestryMemory]
    if query_vec is not None:
        distance_col = TapestryMemory.embedding.cosine_distance(query_vec).label(
            "distance"
        )
        columns.append(distance_col)

    stmt = select(*columns).where(TapestryMemory.status == MemoryStatus.active.value)

    if query_vec is not None:
        stmt = stmt.where(TapestryMemory.embedding.isnot(None))

    if from_date is not None:
        stmt = stmt.where(TapestryMemory.from_date >= from_date)
    if to_date is not None:
        stmt = stmt.where(TapestryMemory.to_date <= to_date)

    if query_vec is not None:
        stmt = stmt.order_by(text("distance"))
    else:
        stmt = stmt.order_by(TapestryMemory.from_date.desc())

    stmt = stmt.limit(top_k)

    result = await session.execute(stmt)
    rows = result.all()

    results: list[MemorySearchResult] = []
    for row in rows:
        if query_vec is not None:
            memory, distance = row
            similarity = 1 - distance
        else:
            (memory,) = row
            similarity = None

        results.append(
            MemorySearchResult(
                id=memory.id,
                content=memory.content,
                from_date=memory.from_date,
                to_date=memory.to_date,
                similarity=similarity,
            )
        )

    return results

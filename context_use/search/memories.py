from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import litellm
from sqlalchemy import select, text

from context_use.db.base import DatabaseBackend
from context_use.llm.models import OpenAIEmbeddingModel
from context_use.memories.models import EMBEDDING_DIMENSIONS, TapestryMemory


@dataclass(frozen=True)
class MemorySearchResult:
    id: str
    content: str
    from_date: date
    to_date: date
    similarity: float | None


async def _embed_query(query: str, api_key: str) -> list[float]:
    model = OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE.value
    response = await litellm.aembedding(model=model, input=[query], api_key=api_key)
    return response.data[0]["embedding"]


async def search_memories(
    db: DatabaseBackend,
    *,
    query: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    top_k: int = 5,
    openai_api_key: str | None = None,
) -> list[MemorySearchResult]:
    """Search memories by semantic similarity, time range, or both.

    Args:
        db: Database backend to query against.
        query: Free-text query for semantic search (requires ``openai_api_key``).
        from_date: Only include memories whose ``from_date >= from_date``.
        to_date: Only include memories whose ``to_date <= to_date``.
        top_k: Maximum number of results to return.
        openai_api_key: Required when *query* is provided.

    Returns:
        A list of :class:`MemorySearchResult` ordered by relevance (semantic)
        or date (time-range only).
    """
    if query is None and from_date is None and to_date is None:
        raise ValueError("Provide at least one of: query, from_date, to_date")

    query_vec: list[float] | None = None
    if query is not None:
        if openai_api_key is None:
            raise ValueError("openai_api_key is required for semantic search")
        query_vec = await _embed_query(query, openai_api_key)
        assert len(query_vec) == EMBEDDING_DIMENSIONS

    session = db.get_session()
    try:
        columns: list = [TapestryMemory]
        if query_vec is not None:
            distance_col = TapestryMemory.embedding.cosine_distance(query_vec).label(
                "distance"
            )
            columns.append(distance_col)

        stmt = select(*columns)

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
    finally:
        await session.close()

from __future__ import annotations

import logging

from sqlalchemy import and_, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from context_use.memories.models import MemoryStatus, TapestryMemory

logger = logging.getLogger(__name__)


class _UnionFind:
    """Simple union-find for merging overlapping candidate sets."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        if x not in self._parent:
            self._parent[x] = x
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb

    def clusters(self) -> list[list[str]]:
        groups: dict[str, list[str]] = {}
        for item in self._parent:
            root = self.find(item)
            groups.setdefault(root, []).append(item)
        return list(groups.values())


async def discover_refinement_clusters(
    seed_memory_ids: list[str],
    db: AsyncSession,
    *,
    date_proximity_days: int = 7,
    similarity_threshold: float = 0.4,
    max_candidates_per_seed: int = 10,
) -> list[list[str]]:
    """Find clusters of active memories that should be refined together.

    For each seed memory, finds existing active memories whose date ranges
    overlap within ``date_proximity_days`` AND whose embedding cosine
    similarity exceeds ``similarity_threshold``. Overlapping candidate sets
    are merged via union-find.

    Returns a list of clusters (each a list of memory IDs), excluding
    single-memory clusters.
    """
    if not seed_memory_ids:
        return []

    seeds_result = await db.execute(
        select(TapestryMemory).where(TapestryMemory.id.in_(seed_memory_ids))
    )
    seeds = list(seeds_result.scalars().all())

    if not seeds:
        return []

    uf = _UnionFind()
    cosine_threshold = 1.0 - similarity_threshold

    for seed in seeds:
        if seed.embedding is None:
            continue

        # Date overlap: candidate.from_date <= seed.to_date + N days
        #           AND candidate.to_date   >= seed.from_date - N days
        proximity = func.make_interval(0, 0, 0, date_proximity_days)

        stmt = (
            select(TapestryMemory.id)
            .where(
                and_(
                    TapestryMemory.status == MemoryStatus.active.value,
                    TapestryMemory.embedding.isnot(None),
                    TapestryMemory.id != seed.id,
                    TapestryMemory.from_date <= literal(seed.to_date) + proximity,
                    TapestryMemory.to_date >= literal(seed.from_date) - proximity,
                    TapestryMemory.embedding.cosine_distance(seed.embedding)
                    < cosine_threshold,
                )
            )
            .order_by(TapestryMemory.embedding.cosine_distance(seed.embedding))
            .limit(max_candidates_per_seed)
        )

        result = await db.execute(stmt)
        candidate_ids = [row[0] for row in result.all()]

        for cid in candidate_ids:
            uf.union(seed.id, cid)

        # Ensure the seed is in the union-find even with no candidates
        uf.find(seed.id)

    # Only return clusters with 2+ memories
    return [c for c in uf.clusters() if len(c) >= 2]

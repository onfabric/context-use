from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from context_use.store.base import Store

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
    store: Store,
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

    seeds = await store.get_memories(seed_memory_ids)
    if not seeds:
        return []

    uf = _UnionFind()

    for seed in seeds:
        if seed.embedding is None:
            continue

        candidate_ids = await store.find_similar_memories(
            seed.id,
            date_proximity_days=date_proximity_days,
            similarity_threshold=similarity_threshold,
            max_candidates=max_candidates_per_seed,
        )

        for cid in candidate_ids:
            uf.union(seed.id, cid)

        uf.find(seed.id)

    return [c for c in uf.clusters() if len(c) >= 2]

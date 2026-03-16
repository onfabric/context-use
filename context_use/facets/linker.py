from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from context_use.models.facet import Facet, MemoryFacet

if TYPE_CHECKING:
    from context_use.store.base import Store

logger = logging.getLogger(__name__)


class SemanticFacetLinker:
    def __init__(self, store: Store, threshold: float = 0.75) -> None:
        self._store = store
        self._threshold = threshold

    async def link(self, facets: list[MemoryFacet]) -> None:
        """Link each facet to a canonical ``Facet``, creating one on miss."""
        for facet in facets:
            assert facet.embedding is not None, (
                f"MemoryFacet {facet.id} has no embedding — embed before linking"
            )
            canonical = await self._store.find_similar_facet(
                facet_type=facet.facet_type,
                embedding=facet.embedding,
                threshold=self._threshold,
            )
            if canonical is None:
                canonical = await self._create_canonical(facet)
            facet.facet_id = canonical.id
            await self._store.update_memory_facet(facet)
            logger.debug(
                "Linked memory_facet %s → facet %s (%s: %s)",
                facet.id,
                canonical.id,
                canonical.facet_type,
                canonical.facet_canonical,
            )

    async def _create_canonical(self, facet: MemoryFacet) -> Facet:
        assert facet.embedding is not None
        async with self._store.atomic():
            canonical = await self._store.create_facet(
                Facet(
                    facet_type=facet.facet_type,
                    facet_canonical=facet.facet_value,
                )
            )
            await self._store.create_facet_embedding(canonical.id, facet.embedding)
        return canonical

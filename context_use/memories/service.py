from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from context_use.models.memory import MemoryStatus, MemorySummary, TapestryMemory
from context_use.models.utils import generate_uuidv4
from context_use.store.base import MemorySearchResult

if TYPE_CHECKING:
    from context_use.llm.base import BaseLLMClient
    from context_use.store.base import Store


class MemoryService:
    def __init__(self, store: Store, llm_client: BaseLLMClient) -> None:
        self._store = store
        self._llm_client = llm_client

    async def list_memories(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int | None = None,
    ) -> list[MemorySummary]:
        memories = await self._store.list_memories(
            status=MemoryStatus.active.value,
            from_date=from_date,
            limit=limit,
        )
        if to_date is not None:
            memories = [m for m in memories if m.to_date <= to_date]
        return [
            MemorySummary(
                id=m.id, content=m.content, from_date=m.from_date, to_date=m.to_date
            )
            for m in memories
        ]

    async def search_memories(
        self,
        *,
        query: str,
        from_date: date | None = None,
        to_date: date | None = None,
        top_k: int = 5,
    ) -> list[MemorySearchResult]:
        query_embedding = await self._llm_client.embed_query(query)
        return await self._store.search_memories(
            query_embedding=query_embedding,
            from_date=from_date,
            to_date=to_date,
            top_k=top_k,
        )

    async def get_memory(self, memory_id: str) -> TapestryMemory | None:
        memories = await self._store.get_memories([memory_id])
        return memories[0] if memories else None

    async def update_memory(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> TapestryMemory:
        memories = await self._store.get_memories([memory_id])
        if not memories:
            raise ValueError(f"Memory {memory_id!r} not found")
        if content is None and from_date is None and to_date is None:
            raise ValueError("Provide at least one of: content, from_date, to_date")
        m = memories[0]
        if content is not None:
            m.content = content
            m.embedding = await self._llm_client.embed_query(content)
        if from_date is not None:
            m.from_date = from_date
        if to_date is not None:
            m.to_date = to_date
        await self._store.update_memory(m)
        return m

    async def create_memory(
        self,
        content: str,
        from_date: date,
        to_date: date,
        *,
        source_memory_ids: list[str] | None = None,
    ) -> TapestryMemory:
        embedding = await self._llm_client.embed_query(content)
        memory = TapestryMemory(
            content=content,
            from_date=from_date,
            to_date=to_date,
            group_id=generate_uuidv4(),
            status=MemoryStatus.active.value,
            source_memory_ids=source_memory_ids,
            embedding=embedding,
        )
        return await self._store.create_memory(memory)

    async def archive_memories(
        self,
        memory_ids: list[str],
        *,
        superseded_by: str | None = None,
    ) -> list[str]:
        memories = await self._store.get_memories(memory_ids)
        archived_ids: list[str] = []
        for m in memories:
            m.status = MemoryStatus.superseded.value
            if superseded_by:
                m.superseded_by = superseded_by
            await self._store.update_memory(m)
            archived_ids.append(m.id)
        return archived_ids

    async def count_memories(self) -> int:
        return await self._store.count_memories(status=MemoryStatus.active.value)

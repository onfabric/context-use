"""Protocol describing the memory operations the agent tools require."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from context_use.models.memory import MemorySummary, TapestryMemory
from context_use.models.user_profile import UserProfile
from context_use.store.base import MemorySearchResult


class MemoryOperations(Protocol):
    """Interface required by :func:`~context_use.agent.tools.make_agent_tools`."""

    async def list_memories(
        self,
        *,
        from_date: date,
        to_date: date,
        limit: int | None = None,
    ) -> list[MemorySummary]: ...

    async def search_memories(
        self,
        *,
        query: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        top_k: int = 5,
    ) -> list[MemorySearchResult]: ...

    async def get_memory(self, memory_id: str) -> TapestryMemory | None: ...

    async def update_memory(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> TapestryMemory: ...

    async def create_memory(
        self,
        content: str,
        from_date: date,
        to_date: date,
        *,
        source_memory_ids: list[str] | None = None,
    ) -> TapestryMemory: ...

    async def archive_memories(
        self,
        memory_ids: list[str],
        *,
        superseded_by: str | None = None,
    ) -> list[str]: ...

    async def get_user_profile(self) -> UserProfile | None: ...

    async def save_user_profile(self, content: str) -> UserProfile: ...

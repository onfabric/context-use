from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from types import TracebackType

from context_use.batch.grouper import ThreadGroup
from context_use.etl.core.types import ThreadRow
from context_use.models import (
    Archive,
    Batch,
    EtlTask,
    TapestryMemory,
    Thread,
    UserProfile,
)


@dataclass(frozen=True)
class MemorySearchResult:
    """A memory search hit with optional similarity score."""

    id: str
    content: str
    from_date: date
    to_date: date
    similarity: float | None


class Store(ABC):
    """Abstract store for all context_use domain entities.

    Implementations must override every ``@abstractmethod``.
    The default ``atomic()`` is a no-op suitable for in-memory stores;
    database-backed stores should override it to provide a transactional
    boundary.
    """

    # ── Lifecycle ────────────────────────────────────────────────────

    @abstractmethod
    async def init(self) -> None:
        """Create tables / indices (idempotent)."""
        ...

    @abstractmethod
    async def reset(self) -> None:
        """Drop all data and recreate from scratch."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release any held resources (connections, file handles)."""
        ...

    async def __aenter__(self) -> Store:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    @asynccontextmanager
    async def atomic(self) -> AsyncIterator[None]:
        """Wrap multiple operations in a single commit.

        The default implementation is a no-op (each operation is
        auto-committed).  Database-backed stores override this to open
        a session, yield, then commit-or-rollback.
        """
        yield

    # ── Archives ─────────────────────────────────────────────────────

    @abstractmethod
    async def create_archive(self, archive: Archive) -> Archive:
        """Persist a new archive and return it (``id`` is set)."""
        ...

    @abstractmethod
    async def get_archive(self, archive_id: str) -> Archive | None:
        """Return an archive by ID, or ``None``."""
        ...

    @abstractmethod
    async def update_archive(self, archive: Archive) -> None:
        """Persist changes to an existing archive."""
        ...

    # ── ETL Tasks ────────────────────────────────────────────────────

    @abstractmethod
    async def create_task(self, task: EtlTask) -> EtlTask:
        """Persist a new ETL task and return it."""
        ...

    @abstractmethod
    async def get_task(self, task_id: str) -> EtlTask | None:
        """Return a task by ID, or ``None``."""
        ...

    @abstractmethod
    async def update_task(self, task: EtlTask) -> None:
        """Persist changes to an existing task."""
        ...

    # ── Threads ──────────────────────────────────────────────────────

    @abstractmethod
    async def insert_threads(self, rows: list[ThreadRow], task_id: str) -> int:
        """Insert threads, deduplicating on ``unique_key``.

        Returns the number of rows actually inserted (after dedup).
        """
        ...

    @abstractmethod
    async def get_unprocessed_threads(
        self,
        *,
        interaction_types: list[str] | None = None,
    ) -> list[Thread]:
        """Return threads not yet assigned to any batch.

        If *interaction_types* is given, only threads whose
        ``interaction_type`` is in that list are returned.
        Results are ordered by ``asat``, then ``id``.
        """
        ...

    # ── Batches ──────────────────────────────────────────────────────

    @abstractmethod
    async def create_batch(self, batch: Batch, groups: list[ThreadGroup]) -> Batch:
        """Persist a batch and its thread-group mappings.

        The store creates ``BatchThread`` records internally from *groups*.
        """
        ...

    @abstractmethod
    async def get_batch(self, batch_id: str) -> Batch | None:
        """Return a batch by ID, or ``None``."""
        ...

    @abstractmethod
    async def update_batch(self, batch: Batch) -> None:
        """Persist changes to an existing batch (typically state updates)."""
        ...

    @abstractmethod
    async def get_batch_groups(self, batch_id: str) -> list[ThreadGroup]:
        """Return threads for a batch, organised into groups."""
        ...

    # ── Memories ─────────────────────────────────────────────────────

    @abstractmethod
    async def create_memory(self, memory: TapestryMemory) -> TapestryMemory:
        """Persist a new memory and return it (``id`` is set)."""
        ...

    @abstractmethod
    async def get_memories(self, ids: list[str]) -> list[TapestryMemory]:
        """Return memories by ID (missing IDs are silently skipped)."""
        ...

    @abstractmethod
    async def get_unembedded_memories(self, ids: list[str]) -> list[TapestryMemory]:
        """Return memories from *ids* that have no embedding."""
        ...

    @abstractmethod
    async def update_memory(self, memory: TapestryMemory) -> None:
        """Persist changes to an existing memory."""
        ...

    @abstractmethod
    async def list_memories(
        self,
        *,
        status: str | None = None,
        from_date: date | None = None,
        limit: int | None = None,
    ) -> list[TapestryMemory]:
        """Return memories ordered by ``from_date``, with optional filters."""
        ...

    @abstractmethod
    async def count_memories(self, *, status: str | None = None) -> int:
        """Count memories, optionally filtered by status."""
        ...

    @abstractmethod
    async def search_memories(
        self,
        *,
        query_embedding: list[float] | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        top_k: int = 5,
    ) -> list[MemorySearchResult]:
        """Search memories by semantic similarity, date range, or both.

        When *query_embedding* is given, results are ordered by cosine
        similarity (descending).  Otherwise they are ordered by
        ``from_date`` descending.
        """
        ...

    # ── User Profile ──────────────────────────────────────────────────

    @abstractmethod
    async def get_user_profile(self) -> UserProfile | None:
        """Return the single user profile, or ``None`` if not yet created."""
        ...

    @abstractmethod
    async def upsert_user_profile(self, profile: UserProfile) -> UserProfile:
        """Create or replace the single user profile.

        If a profile already exists its ``content`` and ``updated_at``
        are overwritten; ``created_at`` is preserved.  Returns the
        persisted profile.
        """
        ...

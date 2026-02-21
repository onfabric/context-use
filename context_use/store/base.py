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
    TapestryProfile,
    Thread,
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

    @abstractmethod
    async def list_archives(self, *, status: str | None = None) -> list[Archive]:
        """Return archives, optionally filtered by status."""
        ...

    @abstractmethod
    async def count_threads_for_archive(self, archive_id: str) -> int:
        """Count threads belonging to an archive (via its ETL tasks)."""
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

    @abstractmethod
    async def get_tasks_by_archive(self, archive_ids: list[str]) -> list[EtlTask]:
        """Return all tasks whose ``archive_id`` is in *archive_ids*."""
        ...

    # ── Threads ──────────────────────────────────────────────────────

    @abstractmethod
    async def insert_threads(self, rows: list[ThreadRow], task_id: str) -> int:
        """Insert threads, deduplicating on ``unique_key``.

        Returns the number of rows actually inserted (after dedup).
        """
        ...

    @abstractmethod
    async def get_threads_by_task(self, task_ids: list[str]) -> list[Thread]:
        """
        Return threads whose ``etl_task_id`` is in *task_ids*,
        ordered by ``asat``.
        """
        ...

    # ── Batches ──────────────────────────────────────────────────────

    @abstractmethod
    async def create_batch(self, batch: Batch, groups: list[ThreadGroup]) -> Batch:
        """Persist a batch and its thread-group mappings.

        The store creates ``BatchThread`` records internally from *groups*.
        Pass an empty list for batches that carry group info in state
        (e.g. refinement batches).
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

    @abstractmethod
    async def get_refinable_memory_ids(self) -> list[str]:
        """Return IDs of active, embedded memories that have not been refined."""
        ...

    @abstractmethod
    async def find_similar_memories(
        self,
        seed_id: str,
        *,
        date_proximity_days: int = 7,
        similarity_threshold: float = 0.4,
        max_candidates: int = 10,
    ) -> list[str]:
        """Find memory IDs similar to *seed_id* by date proximity and embedding."""
        ...

    # ── Profiles ─────────────────────────────────────────────────────

    @abstractmethod
    async def get_latest_profile(self) -> TapestryProfile | None:
        """Return the most recently generated profile, or ``None``."""
        ...

    @abstractmethod
    async def save_profile(self, profile: TapestryProfile) -> None:
        """Insert or update a profile."""
        ...

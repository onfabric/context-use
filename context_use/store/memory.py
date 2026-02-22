from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta

from context_use.batch.grouper import ThreadGroup
from context_use.etl.core.types import ThreadRow
from context_use.models import (
    Archive,
    Batch,
    BatchThread,
    EtlTask,
    MemoryStatus,
    TapestryMemory,
    TapestryProfile,
    Thread,
)
from context_use.store.base import MemorySearchResult, Store


class InMemoryStore(Store):
    """Store backed by plain Python dicts.

    Thread-safe within a single asyncio event loop (no concurrent
    mutation).  ``atomic()`` is inherited as a no-op from the base class.
    """

    def __init__(self) -> None:
        self._archives: dict[str, Archive] = {}
        self._tasks: dict[str, EtlTask] = {}
        self._threads: dict[str, Thread] = {}
        self._thread_unique_keys: set[str] = set()
        self._batches: dict[str, Batch] = {}
        self._batch_threads: list[BatchThread] = []
        self._memories: dict[str, TapestryMemory] = {}
        self._profiles: dict[str, TapestryProfile] = {}

    # ── Lifecycle ────────────────────────────────────────────────────

    async def init(self) -> None:
        pass

    async def reset(self) -> None:
        self.__init__()  # type: ignore[misc]

    async def close(self) -> None:
        pass

    # ── Archives ─────────────────────────────────────────────────────

    async def create_archive(self, archive: Archive) -> Archive:
        self._archives[archive.id] = archive
        return archive

    async def get_archive(self, archive_id: str) -> Archive | None:
        return self._archives.get(archive_id)

    async def update_archive(self, archive: Archive) -> None:
        self._archives[archive.id] = archive

    async def list_archives(self, *, status: str | None = None) -> list[Archive]:
        archives = list(self._archives.values())
        if status is not None:
            archives = [a for a in archives if a.status == status]
        return sorted(archives, key=lambda a: a.created_at)

    async def count_threads_for_archive(self, archive_id: str) -> int:
        task_ids = {t.id for t in self._tasks.values() if t.archive_id == archive_id}
        return sum(1 for t in self._threads.values() if t.etl_task_id in task_ids)

    # ── ETL Tasks ────────────────────────────────────────────────────

    async def create_task(self, task: EtlTask) -> EtlTask:
        self._tasks[task.id] = task
        return task

    async def get_task(self, task_id: str) -> EtlTask | None:
        return self._tasks.get(task_id)

    async def update_task(self, task: EtlTask) -> None:
        self._tasks[task.id] = task

    async def get_tasks_by_archive(self, archive_ids: list[str]) -> list[EtlTask]:
        ids = set(archive_ids)
        return [t for t in self._tasks.values() if t.archive_id in ids]

    # ── Threads ──────────────────────────────────────────────────────

    async def insert_threads(self, rows: list[ThreadRow], task_id: str) -> int:
        count = 0
        for row in rows:
            if row.unique_key in self._thread_unique_keys:
                continue
            thread = Thread(
                unique_key=row.unique_key,
                provider=row.provider,
                interaction_type=row.interaction_type,
                preview=row.preview,
                payload=row.payload,
                version=row.version,
                asat=row.asat,
                etl_task_id=task_id,
                asset_uri=row.asset_uri,
                source=row.source,
            )
            self._threads[thread.id] = thread
            self._thread_unique_keys.add(row.unique_key)
            count += 1
        return count

    async def get_threads_by_task(self, task_ids: list[str]) -> list[Thread]:
        ids = set(task_ids)
        threads = [t for t in self._threads.values() if t.etl_task_id in ids]
        return sorted(threads, key=lambda t: (t.asat, t.id))

    # ── Batches ──────────────────────────────────────────────────────

    async def create_batch(self, batch: Batch, groups: list[ThreadGroup]) -> Batch:
        self._batches[batch.id] = batch
        for grp in groups:
            for thread in grp.threads:
                self._batch_threads.append(
                    BatchThread(
                        batch_id=batch.id,
                        thread_id=thread.id,
                        group_id=grp.group_id,
                    )
                )
        return batch

    async def get_batch(self, batch_id: str) -> Batch | None:
        return self._batches.get(batch_id)

    async def update_batch(self, batch: Batch) -> None:
        self._batches[batch.id] = batch

    async def get_batch_groups(self, batch_id: str) -> list[ThreadGroup]:
        groups_map: dict[str, list[Thread]] = defaultdict(list)
        for bt in self._batch_threads:
            if bt.batch_id != batch_id:
                continue
            thread = self._threads.get(bt.thread_id)
            if thread is not None:
                groups_map[bt.group_id].append(thread)

        return [
            ThreadGroup(
                threads=sorted(threads, key=lambda t: t.asat),  # type: ignore[arg-type]
                group_id=gid,
            )
            for gid, threads in groups_map.items()
        ]

    # ── Memories ─────────────────────────────────────────────────────

    async def create_memory(self, memory: TapestryMemory) -> TapestryMemory:
        self._memories[memory.id] = memory
        return memory

    async def get_memories(self, ids: list[str]) -> list[TapestryMemory]:
        return [self._memories[mid] for mid in ids if mid in self._memories]

    async def get_unembedded_memories(self, ids: list[str]) -> list[TapestryMemory]:
        return [
            self._memories[mid]
            for mid in ids
            if mid in self._memories and self._memories[mid].embedding is None
        ]

    async def update_memory(self, memory: TapestryMemory) -> None:
        self._memories[memory.id] = memory

    async def list_memories(
        self,
        *,
        status: str | None = None,
        from_date: date | None = None,
        limit: int | None = None,
    ) -> list[TapestryMemory]:
        result = list(self._memories.values())
        if status is not None:
            result = [m for m in result if m.status == status]
        if from_date is not None:
            result = [m for m in result if m.from_date >= from_date]
        result.sort(key=lambda m: m.from_date)
        if limit is not None:
            result = result[:limit]
        return result

    async def count_memories(self, *, status: str | None = None) -> int:
        if status is None:
            return len(self._memories)
        return sum(1 for m in self._memories.values() if m.status == status)

    async def search_memories(
        self,
        *,
        query_embedding: list[float] | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        top_k: int = 5,
    ) -> list[MemorySearchResult]:
        candidates = [
            m for m in self._memories.values() if m.status == MemoryStatus.active.value
        ]

        if from_date is not None:
            candidates = [m for m in candidates if m.from_date >= from_date]
        if to_date is not None:
            candidates = [m for m in candidates if m.to_date <= to_date]

        if query_embedding is not None:
            candidates = [m for m in candidates if m.embedding is not None]
            scored: list[tuple[TapestryMemory, float]] = []
            for m in candidates:
                assert m.embedding is not None
                sim = _cosine_similarity(query_embedding, m.embedding)
                scored.append((m, sim))
            scored.sort(key=lambda x: x[1], reverse=True)

            return [
                MemorySearchResult(
                    id=m.id,
                    content=m.content,
                    from_date=m.from_date,
                    to_date=m.to_date,
                    similarity=sim,
                )
                for m, sim in scored[:top_k]
            ]

        candidates.sort(key=lambda m: m.from_date, reverse=True)
        return [
            MemorySearchResult(
                id=m.id,
                content=m.content,
                from_date=m.from_date,
                to_date=m.to_date,
                similarity=None,
            )
            for m in candidates[:top_k]
        ]

    async def get_refinable_memory_ids(self) -> list[str]:
        return [
            m.id
            for m in self._memories.values()
            if m.status == MemoryStatus.active.value
            and m.embedding is not None
            and m.source_memory_ids is None
        ]

    async def find_similar_memories(
        self,
        seed_id: str,
        *,
        date_proximity_days: int = 7,
        similarity_threshold: float = 0.4,
        max_candidates: int = 10,
    ) -> list[str]:
        seed = self._memories.get(seed_id)
        if seed is None or seed.embedding is None:
            return []

        proximity = timedelta(days=date_proximity_days)
        cosine_threshold = 1.0 - similarity_threshold

        scored: list[tuple[str, float]] = []
        for m in self._memories.values():
            if m.id == seed_id:
                continue
            if m.status != MemoryStatus.active.value:
                continue
            if m.embedding is None:
                continue
            if m.from_date > seed.to_date + proximity:
                continue
            if m.to_date < seed.from_date - proximity:
                continue

            distance = 1.0 - _cosine_similarity(seed.embedding, m.embedding)
            if distance < cosine_threshold:
                scored.append((m.id, distance))

        scored.sort(key=lambda x: x[1])
        return [mid for mid, _ in scored[:max_candidates]]

    # ── Profiles ─────────────────────────────────────────────────────

    async def get_latest_profile(self) -> TapestryProfile | None:
        if not self._profiles:
            return None
        return max(self._profiles.values(), key=lambda p: p.generated_at)

    async def save_profile(self, profile: TapestryProfile) -> None:
        self._profiles[profile.id] = profile


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)

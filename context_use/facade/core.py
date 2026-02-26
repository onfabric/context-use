"""Main facade for the context_use library."""

from __future__ import annotations

import logging
import zipfile
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from context_use.batch.manager import (
    BatchContext,
    ScheduleInstruction,
    get_manager_for_category,
)
from context_use.facade.types import (
    ArchiveSummary,
    MemorySummary,
    PipelineResult,
    ProfileSummary,
    TaskBreakdown,
)
from context_use.models import Archive, EtlTask
from context_use.models.archive import ArchiveStatus
from context_use.models.batch import Batch, BatchCategory
from context_use.models.etl_task import EtlTaskStatus
from context_use.models.memory import MemoryStatus
from context_use.providers.registry import Provider
from context_use.store.base import MemorySearchResult

if TYPE_CHECKING:
    from datetime import date, datetime

    from context_use.llm.base import BaseLLMClient
    from context_use.storage.base import StorageBackend
    from context_use.store.base import Store

logger = logging.getLogger(__name__)


class ContextUse:
    """Main entry point for the context_use library.

    Provides a unified API for the full pipeline: ingest archives,
    generate memories, refine memories, search, and generate profiles.

    Usage::

        from context_use.storage.disk import DiskStorage
        from context_use.store.memory import InMemoryStore
        from context_use.llm.litellm import LiteLLMBatchClient

        ctx = ContextUse(
            storage=DiskStorage("./data"),
            store=InMemoryStore(),
            llm_client=LiteLLMBatchClient(...),
        )
        await ctx.init()
        result = await ctx.process_archive(Provider.CHATGPT, "/path/to/export.zip")
    """

    def __init__(
        self,
        storage: StorageBackend,
        store: Store,
        llm_client: BaseLLMClient,
    ) -> None:
        self._storage = storage
        self._store = store
        self._llm_client = llm_client

    async def init(self) -> None:
        """Create missing tables / indices (non-destructive)."""
        await self._store.init()

    async def reset(self) -> None:
        """Drop all data and recreate from scratch."""
        await self._store.reset()

    # ── ETL ──────────────────────────────────────────────────────────

    async def process_archive(
        self,
        provider: Provider,
        path: str,
    ) -> PipelineResult:
        """Unzip, discover, and run ETL for the given archive.

        Each ETL task is committed independently so that a failure
        in one task does not lose previously committed work.
        """
        from context_use.etl.core.exceptions import (
            ArchiveProcessingError,
            UnsupportedProviderError,
        )
        from context_use.providers.registry import (
            PROVIDER_REGISTRY,
            get_provider_config,
        )

        if provider not in PROVIDER_REGISTRY:
            raise UnsupportedProviderError(f"Unsupported provider: {provider}")

        provider_cfg = get_provider_config(provider)

        # Phase 1: create archive + discover tasks.
        archive = Archive(
            provider=provider.value,
            status=ArchiveStatus.CREATED.value,
        )
        archive = await self._store.create_archive(archive)
        archive_id = archive.id

        try:
            prefix = f"{archive_id}/"
            self._unzip(path, prefix)

            files = self._storage.list_keys(archive_id)
            archive.file_uris = files

            discovered_tasks = provider_cfg.discover_tasks(
                archive_id, files, provider.value
            )
            if not discovered_tasks:
                logger.warning("No tasks discovered for archive %s", archive_id)

            task_models: list[EtlTask] = []
            for etl_task in discovered_tasks:
                etl_task.status = EtlTaskStatus.CREATED.value
                etl_task.archive_id = archive_id
                etl_task = await self._store.create_task(etl_task)
                task_models.append(etl_task)

            await self._store.update_archive(archive)

        except Exception as exc:
            logger.error("process_archive discovery failed: %s", exc)
            archive.status = ArchiveStatus.FAILED.value
            await self._store.update_archive(archive)
            raise ArchiveProcessingError(str(exc)) from exc

        result = PipelineResult(archive_id=archive_id)

        # Phase 2: run each ETL task.
        for task_model in task_models:
            try:
                pipe_cls = provider_cfg.get_pipe(task_model.interaction_type)
                pipe = pipe_cls()
                count = await self._run_pipe(pipe, task_model)

                task_model.status = EtlTaskStatus.COMPLETED.value
                task_model.uploaded_count = count
                await self._store.update_task(task_model)

                result.tasks_completed += 1
                result.threads_created += count
                result.breakdown.append(
                    TaskBreakdown(
                        interaction_type=task_model.interaction_type,
                        thread_count=count,
                    )
                )

            except Exception as exc:
                logger.error(
                    "ETL failed for %s/%s: %s",
                    provider,
                    task_model.interaction_type,
                    exc,
                )
                task_model.status = EtlTaskStatus.FAILED.value
                await self._store.update_task(task_model)
                result.tasks_failed += 1
                result.errors.append(str(exc))

        # Phase 3: update archive status.
        archive = await self._store.get_archive(archive_id)
        assert archive is not None
        archive.status = (
            ArchiveStatus.COMPLETED.value
            if result.tasks_failed == 0
            else ArchiveStatus.FAILED.value
        )
        await self._store.update_archive(archive)

        return result

    # ── Memory batches ────────────────────────────────────────────────

    async def create_memory_batches(
        self,
        archive_ids: list[str],
        *,
        since: datetime | None = None,
    ) -> list[Batch]:
        """Group threads from archives and create memory batches.

        Threads from all ETL tasks are collected and grouped per
        interaction type using each type's configured grouper.  The
        resulting groups are merged into a single pool and bin-packed
        into batches — so a batch can contain groups from different
        interaction types.

        Returns persisted :class:`Batch` objects ready to be advanced
        via :meth:`advance_batch`.
        """
        from collections import defaultdict

        from context_use.batch.grouper import ThreadGroup
        from context_use.memories.factory import MemoryBatchFactory
        from context_use.models.thread import Thread
        from context_use.providers.registry import get_memory_config

        tasks = await self._store.get_tasks_by_archive(archive_ids)

        task_ids = [t.id for t in tasks]
        if not task_ids:
            return []

        threads = await self._store.get_threads_by_task(task_ids)

        if since is not None:
            threads = [t for t in threads if t.asat >= since]

        if not threads:
            return []

        by_type: dict[str, list[Thread]] = defaultdict(list)
        for t in threads:
            by_type[t.interaction_type].append(t)

        all_groups: list[ThreadGroup] = []
        for interaction_type, type_threads in by_type.items():
            try:
                config = get_memory_config(interaction_type)
            except KeyError:
                logger.info(
                    "No memory config for %s — skipping",
                    interaction_type,
                )
                continue

            grouper = config.create_grouper()
            groups = grouper.group(type_threads)  # type: ignore[arg-type]
            all_groups.extend(groups)

        return await MemoryBatchFactory.create_batches(all_groups, self._store)

    async def create_refinement_batches(self) -> list[Batch]:
        """Discover overlapping memories and create refinement batches.

        Returns persisted :class:`Batch` objects ready to be advanced
        via :meth:`advance_batch`.
        """
        from context_use.memories.refinement.factory import RefinementBatchFactory

        return await RefinementBatchFactory.create_refinement_batches(
            store=self._store,
        )

    async def advance_batch(self, batch_id: str) -> ScheduleInstruction:
        """Advance a batch one step through its state machine.

        The correct manager is resolved from the batch's ``category`` field.
        """
        _ensure_managers_registered()

        batch = await self._store.get_batch(batch_id)
        if batch is None:
            return ScheduleInstruction(stop=True)

        category = BatchCategory(batch.category)
        manager_cls = get_manager_for_category(category)
        manager = manager_cls(batch=batch, ctx=self._batch_context())
        return await manager.try_advance_state()

    # ── Queries ──────────────────────────────────────────────────────

    async def list_archives(self) -> list[ArchiveSummary]:
        """Return summaries of all completed archives."""
        archives = await self._store.list_archives(
            status=ArchiveStatus.COMPLETED.value,
        )

        summaries: list[ArchiveSummary] = []
        for a in archives:
            count = await self._store.count_threads_for_archive(a.id)
            summaries.append(
                ArchiveSummary(
                    id=a.id,
                    provider=a.provider,
                    created_at=a.created_at,
                    thread_count=count,
                )
            )
        return summaries

    async def list_memories(self, *, limit: int | None = None) -> list[MemorySummary]:
        """Return active memories, ordered by date."""
        memories = await self._store.list_memories(
            status=MemoryStatus.active.value,
            limit=limit,
        )

        return [
            MemorySummary(
                id=m.id,
                content=m.content,
                from_date=m.from_date,
                to_date=m.to_date,
            )
            for m in memories
        ]

    async def count_memories(self) -> int:
        """Return the number of active memories."""
        return await self._store.count_memories(status=MemoryStatus.active.value)

    async def search_memories(
        self,
        *,
        query: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        top_k: int = 5,
    ) -> list[MemorySearchResult]:
        """Search memories by semantic similarity, time range, or both."""
        from context_use.search.memories import search_memories

        return await search_memories(
            self._store,
            query=query,
            from_date=from_date,
            to_date=to_date,
            top_k=top_k,
            llm_client=self._llm_client,
        )

    # ── Profile ──────────────────────────────────────────────────────

    async def get_profile(self) -> ProfileSummary | None:
        """Return the most recent profile, or ``None`` if none exists."""
        profile = await self._store.get_latest_profile()
        if profile is None:
            return None

        return ProfileSummary(
            content=profile.content,
            generated_at=profile.generated_at,
            memory_count=profile.memory_count,
        )

    async def generate_profile(
        self,
        *,
        lookback_months: int = 6,
    ) -> ProfileSummary:
        """Generate or regenerate the user profile from active memories."""
        from context_use.profile.generator import generate_profile

        current = await self._store.get_latest_profile()

        profile = await generate_profile(
            self._store,
            self._llm_client,
            current_profile=current,
            lookback_months=lookback_months,
        )

        return ProfileSummary(
            content=profile.content,
            generated_at=profile.generated_at,
            memory_count=profile.memory_count,
        )

    # ── Private helpers ──────────────────────────────────────────────

    def _batch_context(self) -> BatchContext:
        return BatchContext(
            store=self._store,
            llm_client=self._llm_client,
            storage=self._storage,
        )

    async def _run_pipe(self, pipe, etl_task: EtlTask) -> int:
        """Execute an ETL task using a Pipe and persist results via the Store."""
        rows = list(pipe.run(etl_task, self._storage))
        count = await self._store.insert_threads(rows, etl_task.id)

        etl_task.extracted_count = pipe.extracted_count
        etl_task.transformed_count = pipe.transformed_count
        return count

    def _unzip(self, zip_path: str, prefix: str) -> None:
        """Extract a zip archive into storage under *prefix*."""
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = PurePosixPath(info.filename).as_posix()
                key = f"{prefix}{name}"
                data = zf.read(info.filename)
                self._storage.write(key, data)


def _ensure_managers_registered() -> None:
    """Import manager modules to trigger their @register_batch_manager decorators."""
    import context_use.memories.manager  # noqa: F401
    import context_use.memories.refinement.manager  # noqa: F401

"""Main facade for the context_use library."""

from __future__ import annotations

import logging
import zipfile
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from context_use.facade.types import (
    ArchiveSummary,
    MemoriesResult,
    MemorySummary,
    PipelineResult,
    ProfileSummary,
    RefinementResult,
    TaskBreakdown,
)
from context_use.models import Archive, EtlTask
from context_use.models.archive import ArchiveStatus
from context_use.models.etl_task import EtlTaskStatus
from context_use.models.memory import MemoryStatus
from context_use.providers.registry import Provider
from context_use.store.base import MemorySearchResult

if TYPE_CHECKING:
    from datetime import date

    from context_use.llm.base import LLMClient
    from context_use.storage.base import StorageBackend
    from context_use.store.base import Store

logger = logging.getLogger(__name__)


class ContextUse:
    """Main entry point for the context_use library.

    Provides a unified API for the full pipeline: ingest archives,
    generate memories, refine memories, search, and generate profiles.

    Usage::

        ctx = ContextUse.from_config({
            "storage": {"provider": "disk", "config": {"base_path": "./data"}},
            "store": {"provider": "memory"},
            "llm": {"api_key": "sk-..."},
        })
        await ctx.init()
        result = await ctx.process_archive(Provider.CHATGPT, "/path/to/export.zip")
    """

    def __init__(
        self,
        storage: StorageBackend,
        store: Store,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._storage = storage
        self._store = store
        self._llm_client = llm_client

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> ContextUse:
        """Construct a ContextUse instance from a configuration dict."""
        from context_use.config import build_llm, parse_config

        storage, store = parse_config(config)
        llm_client = None
        llm_cfg = config.get("llm", {})
        if llm_cfg.get("api_key"):
            llm_client = build_llm(llm_cfg)
        return cls(storage=storage, store=store, llm_client=llm_client)

    def _require_llm(self) -> LLMClient:
        if self._llm_client is None:
            raise RuntimeError(
                "LLM client not configured. "
                "Provide an api_key in the llm config section."
            )
        return self._llm_client

    async def init(self) -> None:
        """Create missing tables / indices (non-destructive)."""
        await self._store.init()

    async def reset(self) -> None:
        """Drop all data and recreate from scratch."""
        await self._store.reset()

    # kept for backward-compat; delegates to init()
    async def init_db(self) -> None:
        await self.init()

    async def reset_db(self) -> None:
        await self.reset()

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

    # ── Memory generation ────────────────────────────────────────────

    async def generate_memories(
        self,
        archive_ids: list[str],
    ) -> MemoriesResult:
        """Create batches from ETL results and run the memory pipeline.

        Threads from all ETL tasks are collected and grouped per
        interaction type using each type's configured grouper.  The
        resulting groups are merged into a single pool and bin-packed
        into batches — so a batch can contain groups from different
        interaction types.
        """
        from collections import defaultdict

        from context_use.batch.grouper import ThreadGroup
        from context_use.batch.runner import run_pipeline
        from context_use.memories.factory import MemoryBatchFactory
        from context_use.models.thread import Thread
        from context_use.providers.registry import get_memory_config

        _ensure_managers_registered()
        llm = self._require_llm()
        result = MemoriesResult()

        tasks = await self._store.get_tasks_by_archive(archive_ids)
        result.tasks_processed = len(tasks)

        task_ids = [t.id for t in tasks]
        if not task_ids:
            return result

        threads = await self._store.get_threads_by_task(task_ids)

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

        all_batches = await MemoryBatchFactory.create_batches(all_groups, self._store)

        result.batches_created = len(all_batches)

        if all_batches:
            await run_pipeline(
                all_batches,
                store=self._store,
                manager_kwargs={
                    "llm_client": llm,
                    "storage": self._storage,
                    "memory_config_resolver": get_memory_config,
                },
            )

        return result

    # ── Memory refinement ────────────────────────────────────────────

    async def refine_memories(
        self,
        archive_ids: list[str],
    ) -> RefinementResult:
        """Discover and refine overlapping memories from completed archives."""
        from context_use.batch.runner import run_pipeline
        from context_use.memories.refinement.factory import RefinementBatchFactory

        _ensure_managers_registered()
        llm = self._require_llm()
        result = RefinementResult()

        refinement_batches = await RefinementBatchFactory.create_refinement_batches(
            store=self._store,
        )

        result.batches_created = len(refinement_batches)

        if refinement_batches:
            await run_pipeline(
                refinement_batches,
                store=self._store,
                manager_kwargs={"llm_client": llm},
            )

        return result

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

        llm = self._require_llm() if query is not None else None

        return await search_memories(
            self._store,
            query=query,
            from_date=from_date,
            to_date=to_date,
            top_k=top_k,
            llm_client=llm,
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

        llm = self._require_llm()

        current = await self._store.get_latest_profile()

        profile = await generate_profile(
            self._store,
            llm,
            current_profile=current,
            lookback_months=lookback_months,
        )

        return ProfileSummary(
            content=profile.content,
            generated_at=profile.generated_at,
            memory_count=profile.memory_count,
        )

    # ── Conversational agent ─────────────────────────────────────────

    async def ask(self, query: str, *, top_k: int = 10) -> str:
        """Answer a question using the profile and relevant memories."""
        llm = self._require_llm()

        profile = await self.get_profile()
        results = await self.search_memories(query=query, top_k=top_k)

        parts: list[str] = [
            "You are a helpful assistant with access to the user's personal "
            "memories and profile. Answer their question based on the context "
            "below. Be specific and reference dates/details from the memories. "
            "If the context doesn't contain enough information, say so honestly."
        ]

        if profile:
            parts.append(f"\n## User Profile\n\n{profile.content}")

        if results:
            parts.append("\n## Relevant Memories\n")
            for r in results:
                parts.append(f"- [{r.from_date}] {r.content}")

        parts.append(f"\n## Question\n\n{query}")

        return await llm.completion("\n".join(parts))

    # ── Private helpers ──────────────────────────────────────────────

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

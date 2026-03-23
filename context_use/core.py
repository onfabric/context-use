from __future__ import annotations

import logging
import zipfile
from collections import defaultdict
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from context_use.agent.runner import AgentResult, AgentRunner
from context_use.batch.grouper import ThreadGroup
from context_use.batch.manager import (
    BatchContext,
    ScheduleInstruction,
    get_manager_for_category,
)
from context_use.memories.context import GroupContextBuilder
from context_use.memories.factory import MemoryBatchFactory
from context_use.memories.prompt.agent import AgentToolConversationPromptBuilder
from context_use.memories.service import MemoryService
from context_use.models import Archive, EtlTask
from context_use.models.archive import ArchiveStatus
from context_use.models.batch import Batch, BatchCategory
from context_use.models.etl_task import EtlTaskStatus
from context_use.models.memory import MemorySummary, TapestryMemory
from context_use.models.thread import Thread
from context_use.providers.registry import (
    get_memory_config,
    get_memory_interaction_types,
)
from context_use.proxy.threads import messages_to_thread_rows
from context_use.store.base import MemorySearchResult
from context_use.types import PipelineResult, TaskBreakdown

if TYPE_CHECKING:
    from datetime import date, datetime
    from typing import Any

    from context_use.llm.litellm.clients import LiteLLMBase
    from context_use.storage.base import StorageBackend
    from context_use.store.base import Store

logger = logging.getLogger(__name__)


class ContextUse:
    """Main entry point for the context_use library.

    Provides a unified API for the full pipeline: ingest archives,
    generate memories, and search.

    Usage::

        ctx = ContextUse(
            storage=...,   # StorageBackend implementation
            store=...,     # Store implementation
            llm_client=...,  # LiteLLMBase implementation
        )
        await ctx.init()
        from context_use.providers import chatgpt
        result = await ctx.process_archive(chatgpt.PROVIDER, "/path/to/export.zip")
    """

    def __init__(
        self,
        storage: StorageBackend,
        store: Store,
        llm_client: LiteLLMBase,
    ) -> None:
        self._storage = storage
        self._store = store
        self._llm_client = llm_client
        self._memory_service = MemoryService(self._store, self._llm_client)
        self._agent = AgentRunner(
            memory_service=self._memory_service,
            llm_config=llm_client.config,
        )
        self._group_context_builder = GroupContextBuilder(store)

    async def init(self) -> None:
        """Create missing tables / indices (non-destructive)."""
        await self._store.init(
            embedding_dimensions=self._llm_client.config.embedding_model.embedding_dimensions,
        )

    async def reset(self) -> None:
        """Drop all data and recreate from scratch."""
        await self._store.reset()

    # ── ETL ──────────────────────────────────────────────────────────

    async def process_archive(
        self,
        provider: str,
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
        from context_use.providers.registry import get_provider_config

        try:
            provider_cfg = get_provider_config(provider)
        except KeyError as exc:
            raise UnsupportedProviderError(
                f"Unsupported provider: {provider!r}"
            ) from exc

        # Phase 1: create archive + discover tasks.
        archive = Archive(
            provider=provider,
            status=ArchiveStatus.CREATED.value,
        )
        archive = await self._store.create_archive(archive)
        archive_id = archive.id

        try:
            prefix = f"{archive_id}/"
            self._unzip(path, prefix)

            files = self._storage.list_keys(archive_id)
            archive.file_uris = files

            discovered_tasks = provider_cfg.discover_tasks(archive_id, files, provider)
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
                        task_id=task_model.id,
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
        *,
        since: datetime | None = None,
        before: datetime | None = None,
        interaction_types: list[str] | None = None,
    ) -> list[Batch]:
        """Group all unprocessed threads and create memory batches.

        Only threads for interaction types with a registered memory config
        are considered.  Threads are grouped per interaction type using each
        type's configured grouper.  The resulting groups are merged into a
        single pool and bin-packed into batches — so a batch can contain
        groups from different interaction types.

        Returns persisted :class:`Batch` objects ready to be advanced
        via :meth:`advance_batch`.
        """

        supported = get_memory_interaction_types()
        if interaction_types is not None:
            supported = [t for t in supported if t in interaction_types]
        threads = await self._store.get_unprocessed_threads(
            interaction_types=supported,
            since=since,
            before=before,
        )

        if not threads:
            return []

        by_type: dict[str, list[Thread]] = defaultdict(list)
        for t in threads:
            by_type[t.interaction_type].append(t)

        all_groups: list[ThreadGroup] = []
        for interaction_type, type_threads in by_type.items():
            config = get_memory_config(interaction_type)
            grouper = config.create_grouper()
            groups = grouper.group(type_threads)  # type: ignore[arg-type]
            all_groups.extend(groups)

        return await MemoryBatchFactory.create_batches(all_groups, self._store)

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

    async def get_batch(self, batch_id: str) -> Batch | None:
        return await self._store.get_batch(batch_id)

    # ── Personal agent ───────────────────────────────────────────────

    async def run_agent(self, message: str) -> AgentResult:
        return await self._agent.run(message)

    async def generate_memories_from_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        session_id: str | None = None,
    ) -> AgentResult | None:

        rows = messages_to_thread_rows(messages, session_id=session_id)
        if not rows:
            return None

        await self.insert_threads(rows)

        threads = [
            Thread(
                unique_key=r.unique_key,
                provider=r.provider,
                interaction_type=r.interaction_type,
                preview=r.preview,
                payload=r.payload,
                version=r.version,
                asat=r.asat,
                collection_id=r.collection_id,
            )
            for r in rows
        ]

        thread_group = ThreadGroup(threads=threads)
        group_context = await self._group_context_builder.build(thread_group)
        item = AgentToolConversationPromptBuilder(group_context).build()

        return await self.run_agent(item.prompt)

    # ── Memories ──────────────────────────────────────────────────────

    async def list_memories(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int | None = None,
    ) -> list[MemorySummary]:
        """Return active memories, ordered by date."""
        return await self._memory_service.list_memories(
            from_date=from_date, to_date=to_date, limit=limit
        )

    async def get_memory(self, memory_id: str) -> TapestryMemory | None:
        """Return a single memory by ID, or ``None`` if not found."""
        return await self._memory_service.get_memory(memory_id)

    async def update_memory(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> TapestryMemory:
        """Edit an existing memory.

        At least one of *content*, *from_date*, or *to_date* must be supplied.
        When *content* changes the embedding is recomputed automatically.

        Raises:
            ValueError: if the memory does not exist or nothing is updated.
        """
        return await self._memory_service.update_memory(
            memory_id, content=content, from_date=from_date, to_date=to_date
        )

    async def create_memory(
        self,
        content: str,
        from_date: date,
        to_date: date,
        *,
        source_memory_ids: list[str] | None = None,
    ) -> TapestryMemory:
        """Write a new memory to the store with a freshly computed embedding."""
        return await self._memory_service.create_memory(
            content, from_date, to_date, source_memory_ids=source_memory_ids
        )

    async def archive_memories(
        self,
        memory_ids: list[str],
        *,
        superseded_by: str | None = None,
    ) -> list[str]:
        """Mark memories as superseded and return the IDs that were archived."""
        return await self._memory_service.archive_memories(
            memory_ids, superseded_by=superseded_by
        )

    async def count_memories(self) -> int:
        """Return the number of active memories."""
        return await self._memory_service.count_memories()

    async def search_memories(
        self,
        *,
        query: str,
        from_date: date | None = None,
        to_date: date | None = None,
        top_k: int = 5,
    ) -> list[MemorySearchResult]:
        """Search memories by semantic similarity, optionally filtered by date range."""
        return await self._memory_service.search_memories(
            query=query, from_date=from_date, to_date=to_date, top_k=top_k
        )

    # ── Threads ──────────────────────────────────────────────────────

    async def insert_threads(
        self,
        rows: list,
        task_id: str | None = None,
    ) -> list[str]:
        """Insert thread rows into the store, deduplicating on ``unique_key``."""
        return await self._store.insert_threads(rows, task_id)

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

        etl_task.extracted_count = pipe.extracted_count
        etl_task.transformed_count = pipe.transformed_count

        if pipe.extracted_count == 0 and pipe.error_count > 0:
            raise RuntimeError(
                f"All source files failed extraction "
                f"({pipe.extract_error_count} error(s))"
            )

        inserted_ids = await self._store.insert_threads(rows, etl_task.id)
        return len(inserted_ids)

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

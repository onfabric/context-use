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
from context_use.providers.registry import Provider

if TYPE_CHECKING:
    from datetime import date

    from context_use.db.base import DatabaseBackend
    from context_use.llm.base import LLMClient
    from context_use.search.memories import MemorySearchResult
    from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class ContextUse:
    """Main entry point for the context_use library.

    Provides a unified API for the full pipeline: ingest archives,
    generate memories, refine memories, search, and generate profiles.

    Usage::

        ctx = ContextUse.from_config({
            "storage": {"provider": "disk", "config": {"base_path": "./data"}},
            "db": {
                "provider": "postgres",
                "config": {
                    "host": "localhost",
                    "port": 5432,
                    "database": "context_use",
                    "user": "postgres",
                    "password": "postgres",
                },
            },
            "llm": {"api_key": "sk-..."},
        })
        await ctx.init_db()
        result = await ctx.process_archive(Provider.CHATGPT, "/path/to/export.zip")
    """

    def __init__(
        self,
        storage: StorageBackend,
        db: DatabaseBackend,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._storage = storage
        self._db = db
        self._llm_client = llm_client

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> ContextUse:
        """Construct a ContextUse instance from a configuration dict."""
        from context_use.config import build_llm, parse_config

        storage, db = parse_config(config)
        llm_client = None
        llm_cfg = config.get("llm", {})
        if llm_cfg.get("api_key"):
            llm_client = build_llm(llm_cfg)
        return cls(storage=storage, db=db, llm_client=llm_client)

    def _require_llm(self) -> LLMClient:
        if self._llm_client is None:
            raise RuntimeError(
                "LLM client not configured. "
                "Provide an api_key in the llm config section."
            )
        return self._llm_client

    async def init_db(self) -> None:
        """Create all database tables."""
        import context_use.memories.models  # noqa: F401  — register ORM models
        import context_use.profile.models  # noqa: F401

        await self._db.init_db()

    # ── ETL ──────────────────────────────────────────────────────────

    async def process_archive(
        self,
        provider: Provider,
        path: str,
    ) -> PipelineResult:
        """Unzip, discover, and run ETL for the given archive.

        Each ETL task runs in its own database session so that a failure
        in one task does not roll back previously committed work.

        Args:
            provider: Which data provider (ChatGPT, Instagram, ...).
            path: Filesystem path to the .zip archive.

        Returns:
            A PipelineResult summarising the work done.
        """
        from context_use.etl.core.exceptions import (
            ArchiveProcessingError,
            UnsupportedProviderError,
        )
        from context_use.etl.models.archive import Archive, ArchiveStatus
        from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
        from context_use.providers.registry import (
            PROVIDER_REGISTRY,
            get_provider_config,
        )

        if provider not in PROVIDER_REGISTRY:
            raise UnsupportedProviderError(f"Unsupported provider: {provider}")

        provider_cfg = get_provider_config(provider)

        # Phase 1: create archive + discover tasks in a short transaction.
        async with self._db.session_scope() as session:
            archive = Archive(
                provider=provider.value,
                status=ArchiveStatus.CREATED.value,
            )
            session.add(archive)
            await session.flush()
            archive_id = archive.id

            try:
                prefix = f"{archive_id}/"
                self._unzip(path, prefix)

                files = self._storage.list_keys(archive_id)
                archive.file_uris = files

                discovered = provider_cfg.discover_tasks(
                    archive_id, files, provider.value
                )
                if not discovered:
                    logger.warning("No tasks discovered for archive %s", archive_id)

                for etl_task in discovered:
                    etl_task.status = EtlTaskStatus.CREATED.value
                    etl_task.archive = archive
                    session.add(etl_task)

                await session.flush()
                task_ids = [t.id for t in discovered]

            except Exception as exc:
                logger.error("process_archive discovery failed: %s", exc)
                archive.status = ArchiveStatus.FAILED.value
                raise ArchiveProcessingError(str(exc)) from exc

        result = PipelineResult(archive_id=archive_id)

        # Phase 2: run each ETL task in its own session.
        for task_id in task_ids:
            async with self._db.session_scope() as session:
                etl_task = await session.get(EtlTask, task_id)
                assert etl_task is not None

                try:
                    pipe_cls = provider_cfg.get_pipe(etl_task.interaction_type)
                    pipe = pipe_cls()
                    count = await self._run_pipe(pipe, etl_task, session)

                    etl_task.status = EtlTaskStatus.COMPLETED.value
                    etl_task.uploaded_count = count

                    result.tasks_completed += 1
                    result.threads_created += count
                    result.breakdown.append(
                        TaskBreakdown(
                            interaction_type=etl_task.interaction_type,
                            thread_count=count,
                        )
                    )

                except Exception as exc:
                    logger.error(
                        "ETL failed for %s/%s: %s",
                        provider,
                        etl_task.interaction_type,
                        exc,
                    )
                    etl_task.status = EtlTaskStatus.FAILED.value
                    result.tasks_failed += 1
                    result.errors.append(str(exc))

        # Phase 3: update archive status.
        async with self._db.session_scope() as session:
            archive = await session.get(Archive, archive_id)
            assert archive is not None
            archive.status = (
                ArchiveStatus.COMPLETED.value
                if result.tasks_failed == 0
                else ArchiveStatus.FAILED.value
            )

        return result

    # ── Memory generation ────────────────────────────────────────────

    async def generate_memories(
        self,
        archive_ids: list[str],
    ) -> MemoriesResult:
        """Create batches from ETL results and run the memory pipeline.

        Args:
            archive_ids: Archive IDs from prior ``process_archive()`` calls.

        Returns:
            A :class:`MemoriesResult` summarising the work done.
        """
        from sqlalchemy import select

        from context_use.batch.runner import run_pipeline
        from context_use.etl.models.etl_task import EtlTask
        from context_use.memories.factory import MemoryBatchFactory
        from context_use.providers.registry import get_memory_config

        _ensure_managers_registered()
        llm = self._require_llm()
        result = MemoriesResult()

        # Phase 1: batch creation in its own transactional session.
        all_batches: list = []
        async with self._db.session_scope() as session:
            stmt = select(EtlTask).where(EtlTask.archive_id.in_(archive_ids))
            tasks = list((await session.execute(stmt)).scalars().all())
            result.tasks_processed = len(tasks)

            for task in tasks:
                try:
                    config = get_memory_config(task.interaction_type)
                except KeyError:
                    logger.info(
                        "No memory config for %s — skipping",
                        task.interaction_type,
                    )
                    continue

                grouper = config.create_grouper()
                batches = await MemoryBatchFactory.create_batches(
                    etl_task_id=task.id,
                    db=session,
                    grouper=grouper,
                )
                all_batches.extend(batches)

        result.batches_created = len(all_batches)

        # Phase 2: run pipeline — each manager creates its own sessions.
        if all_batches:
            await run_pipeline(
                all_batches,
                db_backend=self._db,
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
        """Discover and refine overlapping memories from completed archives.

        Args:
            archive_ids: Archive IDs whose memories should be refined.

        Returns:
            A :class:`RefinementResult` summarising the work done.
        """
        from sqlalchemy import select

        from context_use.batch.models import Batch, BatchCategory
        from context_use.batch.runner import run_pipeline
        from context_use.etl.models.etl_task import EtlTask
        from context_use.memories.refinement.factory import RefinementBatchFactory

        _ensure_managers_registered()
        llm = self._require_llm()
        result = RefinementResult()

        # Phase 1: batch creation in its own transactional session.
        refinement_batches: list[Batch] = []
        async with self._db.session_scope() as session:
            stmt = (
                select(Batch)
                .where(Batch.category == BatchCategory.memories.value)
                .join(EtlTask, EtlTask.id == Batch.etl_task_id)
                .where(EtlTask.archive_id.in_(archive_ids))
            )
            memory_batches = list((await session.execute(stmt)).scalars().all())

            completed = [b for b in memory_batches if b.current_status == "COMPLETE"]

            if not completed:
                logger.info("No completed memory batches for refinement")
                return result

            refinement_batches = (
                await RefinementBatchFactory.create_from_memory_batches(
                    completed_batches=completed, db=session
                )
            )

        result.batches_created = len(refinement_batches)

        # Phase 2: run pipeline — each manager creates its own sessions.
        if refinement_batches:
            await run_pipeline(
                refinement_batches,
                db_backend=self._db,
                manager_kwargs={"llm_client": llm},
            )

        return result

    # ── Queries ──────────────────────────────────────────────────────

    async def list_archives(self) -> list[ArchiveSummary]:
        """Return summaries of all completed archives."""
        from sqlalchemy import func, select

        from context_use.etl.models.archive import Archive, ArchiveStatus
        from context_use.etl.models.etl_task import EtlTask
        from context_use.etl.models.thread import Thread

        async with self._db.session_scope() as session:
            stmt = (
                select(
                    Archive.id,
                    Archive.provider,
                    Archive.created_at,
                    func.count(Thread.id).label("thread_count"),
                )
                .where(Archive.status == ArchiveStatus.COMPLETED.value)
                .outerjoin(EtlTask, EtlTask.archive_id == Archive.id)
                .outerjoin(Thread, Thread.etl_task_id == EtlTask.id)
                .group_by(Archive.id, Archive.provider, Archive.created_at)
                .order_by(Archive.created_at)
            )
            rows = (await session.execute(stmt)).all()

        return [
            ArchiveSummary(
                id=aid,
                provider=prov,
                created_at=ts,
                thread_count=cnt,
            )
            for aid, prov, ts, cnt in rows
        ]

    async def list_memories(self, *, limit: int | None = None) -> list[MemorySummary]:
        """Return active memories, ordered by date.

        Args:
            limit: Maximum number of memories to return.
        """
        from sqlalchemy import select

        from context_use.memories.models import MemoryStatus, TapestryMemory

        async with self._db.session_scope() as session:
            stmt = (
                select(TapestryMemory)
                .where(TapestryMemory.status == MemoryStatus.active.value)
                .order_by(TapestryMemory.from_date)
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            memories = list((await session.execute(stmt)).scalars().all())

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
        from sqlalchemy import func, select

        from context_use.memories.models import MemoryStatus, TapestryMemory

        async with self._db.session_scope() as session:
            stmt = (
                select(func.count())
                .select_from(TapestryMemory)
                .where(TapestryMemory.status == MemoryStatus.active.value)
            )
            return (await session.execute(stmt)).scalar() or 0

    async def search_memories(
        self,
        *,
        query: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        top_k: int = 5,
    ) -> list[MemorySearchResult]:
        """Search memories by semantic similarity, time range, or both.

        Args:
            query: Free-text query for semantic search (requires LLM client).
            from_date: Only include memories whose ``from_date >= from_date``.
            to_date: Only include memories whose ``to_date <= to_date``.
            top_k: Maximum number of results to return.
        """
        from context_use.search.memories import search_memories

        llm = self._require_llm() if query is not None else None

        async with self._db.session_scope() as session:
            return await search_memories(
                session,
                query=query,
                from_date=from_date,
                to_date=to_date,
                top_k=top_k,
                llm_client=llm,
            )

    # ── Profile ──────────────────────────────────────────────────────

    async def get_profile(self) -> ProfileSummary | None:
        """Return the most recent profile, or ``None`` if none exists."""
        from sqlalchemy import select

        from context_use.profile.models import TapestryProfile

        async with self._db.session_scope() as session:
            result = await session.execute(
                select(TapestryProfile)
                .order_by(TapestryProfile.generated_at.desc())
                .limit(1)
            )
            profile = result.scalar_one_or_none()

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
        """Generate or regenerate the user profile from active memories.

        Args:
            lookback_months: How far back to look for memories.

        Returns:
            The generated profile summary.
        """
        from context_use.profile.generator import generate_profile

        llm = self._require_llm()

        async with self._db.session_scope() as session:
            profile = await generate_profile(
                session,
                llm,
                lookback_months=lookback_months,
            )

        return ProfileSummary(
            content=profile.content,
            generated_at=profile.generated_at,
            memory_count=profile.memory_count,
        )

    # ── Conversational agent ─────────────────────────────────────────

    async def ask(self, query: str, *, top_k: int = 10) -> str:
        """Answer a question using the profile and relevant memories.

        Builds a RAG prompt from the current profile and the most
        relevant memories, then calls the LLM for a response.

        Args:
            query: The user's question.
            top_k: Number of memories to include as context.
        """
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

    async def _run_pipe(self, pipe, etl_task, session) -> int:
        """Execute an ETL task using a Pipe + Loader."""
        from context_use.etl.core.loader import DbLoader
        from context_use.etl.models.etl_task import EtlTaskStatus

        loader = DbLoader(session=session)
        etl_task.status = EtlTaskStatus.EXTRACTING.value
        count = await loader.load(pipe.run(etl_task, self._storage), etl_task)

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

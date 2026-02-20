from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import context_use.memories.manager  # noqa: F401 — registers MemoryBatchManager
import context_use.memories.refinement.manager  # noqa: F401 — registers RefinementBatchManager
from context_use.batch.runner import run_pipeline
from context_use.config import parse_config
from context_use.db.base import DatabaseBackend
from context_use.etl.core.exceptions import (
    ArchiveProcessingError,
    UnsupportedProviderError,
)
from context_use.etl.core.loader import DbLoader
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import PipelineResult
from context_use.etl.models.archive import Archive, ArchiveStatus
from context_use.etl.models.etl_task import EtlTask, EtlTaskStatus
from context_use.memories.factory import MemoryBatchFactory
from context_use.memories.refinement.factory import RefinementBatchFactory
from context_use.providers.registry import (
    PROVIDER_REGISTRY,
    Provider,
    get_memory_config,
    get_provider_config,
)
from context_use.storage.base import StorageBackend

if TYPE_CHECKING:
    from context_use.llm.base import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class MemoriesResult:
    """Result returned from :meth:`ContextUse.generate_memories`."""

    tasks_processed: int = 0
    batches_created: int = 0
    errors: list[str] = field(default_factory=list)


class ContextUse:
    """Main entry point for the context_use library.

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
        })
        await ctx.init_db()
        result = await ctx.process_archive(Provider.CHATGPT, "/path/to/export.zip")
    """

    def __init__(self, storage: StorageBackend, db: DatabaseBackend) -> None:
        self._storage = storage
        self._db = db

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> ContextUse:
        """Construct a ContextUse instance from a configuration dict."""
        storage, db = parse_config(config)
        return cls(storage=storage, db=db)

    async def init_db(self) -> None:
        await self._db.init_db()

    async def process_archive(
        self,
        provider: Provider,
        path: str,
    ) -> PipelineResult:
        """Unzip, discover, and run ETL for the given archive.

        Args:
            provider: Which data provider (ChatGPT, Instagram, …).
            path: Filesystem path to the .zip archive.

        Returns:
            A PipelineResult summarising the work done.
        """
        if provider not in PROVIDER_REGISTRY:
            raise UnsupportedProviderError(f"Unsupported provider: {provider}")

        provider_cfg = get_provider_config(provider)

        async with self._db.session_scope() as session:
            archive = Archive(
                provider=provider.value,
                status=ArchiveStatus.CREATED.value,
            )
            session.add(archive)
            await session.flush()

            result = PipelineResult(archive_id=archive.id)

            try:
                prefix = f"{archive.id}/"
                self._unzip(path, prefix)

                files = self._storage.list_keys(archive.id)
                archive.file_uris = files

                etl_tasks = provider_cfg.discover_tasks(
                    archive.id, files, provider.value
                )

                if not etl_tasks:
                    logger.warning("No tasks discovered for archive %s", archive.id)

                for etl_task in etl_tasks:
                    etl_task.status = EtlTaskStatus.CREATED.value
                    etl_task.archive = archive
                    session.add(etl_task)
                    await session.flush()

                    try:
                        pipe_cls = provider_cfg.get_pipe(etl_task.interaction_type)
                        count = await self._run_pipe(pipe_cls(), etl_task, session)

                        etl_task.status = EtlTaskStatus.COMPLETED.value
                        etl_task.uploaded_count = count

                        result.tasks_completed += 1
                        result.threads_created += count

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

                archive.status = (
                    ArchiveStatus.COMPLETED.value
                    if result.tasks_failed == 0
                    else ArchiveStatus.FAILED.value
                )

            except Exception as exc:
                logger.error("process_archive failed: %s", exc)
                archive.status = ArchiveStatus.FAILED.value
                raise ArchiveProcessingError(str(exc)) from exc

        return result

    async def generate_memories(
        self,
        archive_ids: list[str],
        llm_client: LLMClient,
    ) -> MemoriesResult:
        """Create batches from ETL results and run the memory pipeline.

        Looks up completed ETL tasks for the given archives, groups their
        threads according to each interaction type's ``MemoryConfig``,
        creates batches, and drives them through the memory state machine
        (generate → embed → complete).

        Args:
            archive_ids: Archive IDs from prior ``process_archive()`` calls.
            llm_client: LLM client for memory generation and embedding.

        Returns:
            A :class:`MemoriesResult` summarising the work done.
        """
        result = MemoriesResult()

        async with self._db.session_scope() as session:
            stmt = select(EtlTask).where(EtlTask.archive_id.in_(archive_ids))
            tasks = list((await session.execute(stmt)).scalars().all())
            result.tasks_processed = len(tasks)

            all_batches = []
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

            if all_batches:
                await run_pipeline(
                    all_batches,
                    db=session,
                    manager_kwargs={
                        "llm_client": llm_client,
                        "storage": self._storage,
                    },
                )

                refinement_batches = (
                    await RefinementBatchFactory.create_from_memory_batches(
                        completed_batches=all_batches, db=session
                    )
                )
                if refinement_batches:
                    await run_pipeline(
                        refinement_batches,
                        db=session,
                        manager_kwargs={"llm_client": llm_client},
                    )

        return result

    async def _run_pipe(
        self,
        pipe: Pipe,
        etl_task: EtlTask,
        session: AsyncSession,
    ) -> int:
        """Execute an ETL task using a Pipe + Loader."""
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

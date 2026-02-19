from __future__ import annotations

import logging
import zipfile
from pathlib import PurePosixPath
from typing import Any

from context_use.config import parse_config
from context_use.db.base import DatabaseBackend
from context_use.etl.core.etl import ETLPipeline, UploadStrategy
from context_use.etl.core.exceptions import (
    ArchiveProcessingError,
    UnsupportedProviderError,
)
from context_use.etl.core.types import PipelineResult
from context_use.etl.models.archive import Archive, ArchiveStatus
from context_use.etl.models.etl_task import EtlTaskStatus
from context_use.etl.providers.registry import (
    PROVIDER_REGISTRY,
    Provider,
    get_provider_config,
)
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


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

                orchestrator = provider_cfg.orchestration()
                etl_tasks = orchestrator.discover_tasks(
                    archive.id, files, provider.value
                )

                if not etl_tasks:
                    logger.warning("No tasks discovered for archive %s", archive.id)

                for etl_task in etl_tasks:
                    it_cfg = provider_cfg.interaction_types.get(
                        etl_task.interaction_type
                    )
                    if it_cfg is None:
                        logger.warning(
                            "No strategy for interaction_type=%s",
                            etl_task.interaction_type,
                        )
                        continue

                    etl_task.status = EtlTaskStatus.CREATED.value
                    etl_task.archive = archive
                    session.add(etl_task)
                    await session.flush()

                    try:
                        pipeline = ETLPipeline(
                            extraction=it_cfg.extraction(),
                            transform=it_cfg.transform(),
                            upload=UploadStrategy(),
                            storage=self._storage,
                            session=session,
                        )

                        etl_task.status = EtlTaskStatus.EXTRACTING.value
                        raw = pipeline.extract(etl_task)

                        etl_task.status = EtlTaskStatus.TRANSFORMING.value
                        thread_batches = pipeline.transform(etl_task, raw)

                        etl_task.status = EtlTaskStatus.UPLOADING.value
                        count = await pipeline.upload(etl_task, thread_batches)

                        etl_task.status = EtlTaskStatus.COMPLETED.value
                        etl_task.extracted_count = sum(len(b) for b in raw)
                        etl_task.transformed_count = sum(len(b) for b in thread_batches)
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

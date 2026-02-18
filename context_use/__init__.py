"""context_use – configurable ETL library for processing data archives."""

from __future__ import annotations

import logging
import uuid
import zipfile
from pathlib import PurePosixPath
from typing import Any

from context_use.config import parse_config
from context_use.core.etl import ETLPipeline, UploadStrategy
from context_use.core.exceptions import (
    ArchiveProcessingError,
    UnsupportedProviderError,
)
from context_use.core.types import PipelineResult, TaskMetadata
from context_use.db.base import DatabaseBackend
from context_use.models.archive import Archive, ArchiveStatus
from context_use.models.etl_task import EtlTask, EtlTaskStatus
from context_use.providers.registry import (
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
            "db":      {"provider": "sqlite", "config": {"path": "./context_use.db"}},
        })
        result = ctx.process_archive(Provider.CHATGPT, "/path/to/export.zip")
    """

    def __init__(self, storage: StorageBackend, db: DatabaseBackend) -> None:
        self._storage = storage
        self._db = db
        self._db.init_db()

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> ContextUse:
        """Construct a ContextUse instance from a configuration dict."""
        storage, db = parse_config(config)
        return cls(storage=storage, db=db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_archive(
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

        # 1. Create Archive record
        archive_id = str(uuid.uuid4())
        with self._db.session_scope() as session:
            archive = Archive(
                id=archive_id,
                provider=provider.value,
                status=ArchiveStatus.CREATED.value,
            )
            session.add(archive)

        result = PipelineResult(archive_id=archive_id)

        try:
            # 2. Unzip into storage
            prefix = f"{archive_id}/"
            self._unzip(path, prefix)

            # 3. Discover files & tasks
            files = self._storage.list_keys(archive_id)
            orchestrator = provider_cfg.orchestration()
            task_descriptors = orchestrator.discover_tasks(archive_id, files)

            if not task_descriptors:
                logger.warning("No tasks discovered for archive %s", archive_id)

            # 4. Run ETL for each task
            for desc in task_descriptors:
                interaction_type = desc["interaction_type"]
                filenames = desc["filenames"]

                it_cfg = provider_cfg.interaction_types.get(interaction_type)
                if it_cfg is None:
                    logger.warning(
                        "No strategy for interaction_type=%s", interaction_type
                    )
                    continue

                etl_task_id = str(uuid.uuid4())
                with self._db.session_scope() as session:
                    etl_task = EtlTask(
                        id=etl_task_id,
                        archive_id=archive_id,
                        provider=provider.value,
                        interaction_type=interaction_type,
                        status=EtlTaskStatus.CREATED.value,
                    )
                    session.add(etl_task)

                task_meta = TaskMetadata(
                    archive_id=archive_id,
                    etl_task_id=etl_task_id,
                    provider=provider.value,
                    interaction_type=interaction_type,
                    filenames=filenames,
                )

                try:
                    pipeline = ETLPipeline(
                        extraction=it_cfg.extraction(),
                        transform=it_cfg.transform(),
                        upload=UploadStrategy(),
                        storage=self._storage,
                        db=self._db,
                    )

                    # Update status as we go
                    self._update_etl_task_status(etl_task_id, EtlTaskStatus.EXTRACTING)
                    raw = pipeline.extract(task_meta)

                    self._update_etl_task_status(
                        etl_task_id, EtlTaskStatus.TRANSFORMING
                    )
                    thread_batches = pipeline.transform(task_meta, raw)

                    self._update_etl_task_status(etl_task_id, EtlTaskStatus.UPLOADING)
                    count = pipeline.upload(task_meta, thread_batches)

                    # Mark completed
                    extracted_count = sum(len(b) for b in raw)
                    transformed_count = sum(len(b) for b in thread_batches)
                    with self._db.session_scope() as session:
                        task_row = session.get(EtlTask, etl_task_id)
                        if task_row:
                            task_row.status = EtlTaskStatus.COMPLETED.value
                            task_row.extracted_count = extracted_count
                            task_row.transformed_count = transformed_count
                            task_row.uploaded_count = count

                    result.tasks_completed += 1
                    result.threads_created += count

                except Exception as exc:
                    logger.error(
                        "ETL failed for %s/%s: %s",
                        provider,
                        interaction_type,
                        exc,
                    )
                    self._update_etl_task_status(etl_task_id, EtlTaskStatus.FAILED)
                    result.tasks_failed += 1
                    result.errors.append(str(exc))

            # 5. Mark archive completed
            final_status = (
                ArchiveStatus.COMPLETED
                if result.tasks_failed == 0
                else ArchiveStatus.FAILED
            )
            with self._db.session_scope() as session:
                archive_row = session.get(Archive, archive_id)
                if archive_row:
                    archive_row.status = final_status.value

        except Exception as exc:
            logger.error("process_archive failed: %s", exc)
            with self._db.session_scope() as session:
                archive_row = session.get(Archive, archive_id)
                if archive_row:
                    archive_row.status = ArchiveStatus.FAILED.value
            raise ArchiveProcessingError(str(exc)) from exc

        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _unzip(self, zip_path: str, prefix: str) -> None:
        """Extract a zip archive into storage under *prefix*."""
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                # Normalise path separators
                name = PurePosixPath(info.filename).as_posix()
                key = f"{prefix}{name}"
                data = zf.read(info.filename)
                self._storage.write(key, data)

    def _update_etl_task_status(
        self,
        etl_task_id: str,
        status: EtlTaskStatus,
    ) -> None:
        with self._db.session_scope() as session:
            task = session.get(EtlTask, etl_task_id)
            if task:
                task.status = status.value

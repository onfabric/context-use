"""ETL pipeline core – strategy ABCs and the synchronous ETLPipeline runner."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import pandas as pd
from sqlalchemy.orm import Session

from context_use.etl.core.exceptions import (
    ExtractionFailedException,
    TransformFailedException,
    UploadFailedException,
)
from context_use.etl.models.etl_task import EtlTask
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategy ABCs
# ---------------------------------------------------------------------------


class OrchestrationStrategy:
    """Decides which ETL tasks to create based on discovered files.

    Sub-classes set ``MANIFEST_MAP``: a dict mapping relative file paths
    (inside the extracted archive) to interaction-type strings.
    """

    MANIFEST_MAP: dict[str, str] = {}

    def discover_tasks(
        self,
        archive_id: str,
        files: list[str],
        provider: str,
    ) -> list[EtlTask]:
        """Return transient ``EtlTask`` objects ready to be added to a session.

        Each task corresponds to one matched file from ``MANIFEST_MAP``.
        """
        tasks: list[EtlTask] = []
        prefix = f"{archive_id}/"
        for pattern, interaction_type in self.MANIFEST_MAP.items():
            # Match exactly: {archive_id}/{pattern}
            expected = f"{prefix}{pattern}"
            matching = [f for f in files if f == expected]
            if matching:
                tasks.append(
                    EtlTask(
                        archive_id=archive_id,
                        provider=provider,
                        interaction_type=interaction_type,
                        source_uri=matching[0],
                    )
                )
        return tasks


class ExtractionStrategy(ABC):
    """Reads raw provider data from storage and yields DataFrames of raw parsed records.

    Does NOT build ActivityStreams payloads – that is the job of ``TransformStrategy``.
    """

    @abstractmethod
    def extract(
        self,
        task: EtlTask,
        storage: StorageBackend,
    ) -> list[pd.DataFrame]:
        """Return a list of DataFrames containing raw parsed records."""
        ...


class TransformStrategy(ABC):
    """Receives raw DataFrames from extract, builds ActivityStreams payloads,
    computes previews / unique keys / timestamps.  Outputs thread-shaped DataFrames.
    """

    @abstractmethod
    def transform(
        self,
        task: EtlTask,
        batches: list[pd.DataFrame],
    ) -> list[pd.DataFrame]:
        """Return DataFrames with thread columns: unique_key, provider,
        interaction_type, preview, payload, source, version, asat, asset_uri.
        """
        ...


class UploadStrategy:
    """Bulk-inserts thread rows into the DB via SQLAlchemy."""

    def upload(
        self,
        task: EtlTask,
        batches: list[pd.DataFrame],
        session: Session,
    ) -> int:
        from context_use.etl.models.thread import Thread

        total = 0
        for df in batches:
            for _, row in df.iterrows():
                thread = Thread(
                    unique_key=row["unique_key"],
                    tapestry_id=task.archive.tapestry_id or None,
                    etl_task_id=task.id,
                    provider=row["provider"],
                    interaction_type=row["interaction_type"],
                    preview=row["preview"],
                    payload=row["payload"],
                    source=row.get("source"),
                    version=row["version"],
                    asat=row["asat"],
                    asset_uri=row.get("asset_uri"),
                )
                session.add(thread)
                total += 1
        return total


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------


class ETLPipeline:
    """Synchronous ETL pipeline that composes the three strategies."""

    def __init__(
        self,
        extraction: ExtractionStrategy,
        transform: TransformStrategy,
        upload: UploadStrategy | None = None,
        storage: StorageBackend | None = None,
        session: Session | None = None,
    ) -> None:
        self._extraction = extraction
        self._transform = transform
        self._upload = upload or UploadStrategy()
        self._storage = storage
        self._session = session

    def extract(self, task: EtlTask) -> list[pd.DataFrame]:
        """Step 1: Extract raw records from provider data."""
        if self._storage is None:
            raise RuntimeError("Storage backend not configured")
        try:
            return self._extraction.extract(task, self._storage)
        except Exception as exc:
            raise ExtractionFailedException(str(exc)) from exc

    def transform(
        self,
        task: EtlTask,
        batches: list[pd.DataFrame],
    ) -> list[pd.DataFrame]:
        """Step 2: Transform raw records into thread-shaped DataFrames."""
        try:
            return self._transform.transform(task, batches)
        except Exception as exc:
            raise TransformFailedException(str(exc)) from exc

    def upload(
        self,
        task: EtlTask,
        batches: list[pd.DataFrame],
    ) -> int:
        """Step 3: Upload thread records to the database."""
        if self._session is None:
            raise RuntimeError("Database session not configured")
        try:
            return self._upload.upload(task, batches, self._session)
        except Exception as exc:
            raise UploadFailedException(str(exc)) from exc

    def run(self, task: EtlTask) -> int:
        """
        Run the full extract -> transform -> upload pipeline.
        Returns count of uploaded threads.
        """
        logger.info("ETL start: %s/%s", task.provider, task.interaction_type)

        raw_batches = self.extract(task)
        logger.info("Extracted %d batches", len(raw_batches))

        thread_batches = self.transform(task, raw_batches)
        logger.info("Transformed %d batches", len(thread_batches))

        count = self.upload(task, thread_batches)
        logger.info("Uploaded %d threads", count)

        return count

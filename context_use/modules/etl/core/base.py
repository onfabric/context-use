import logging
from abc import ABC, abstractmethod

import pandas as pd

from context_use.db.base import DatabaseBackend
from context_use.models.thread import Thread
from context_use.modules.etl.core.exceptions import (
    ExtractionFailedException,
    TransformFailedException,
    UploadFailedException,
)
from context_use.modules.etl.core.types import TaskMetadata
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class OrchestrationStrategy:
    MANIFEST_MAP: dict[str, str] = {}

    def discover_tasks(
        self, archive_id: str, files: list[str]
    ) -> list[dict]:
        discovered: list[dict] = []
        for pattern, interaction_type in self.MANIFEST_MAP.items():
            matched = [
                f
                for f in files
                if f == f"{archive_id}/{pattern}"
            ]
            if matched:
                discovered.append(
                    {
                        "interaction_type": interaction_type,
                        "filenames": matched,
                    }
                )
        return discovered


class ExtractionStrategy(ABC):
    @abstractmethod
    def extract(
        self, task: TaskMetadata, storage: StorageBackend
    ) -> list[pd.DataFrame]: ...


class TransformStrategy(ABC):
    @abstractmethod
    def transform(
        self, task: TaskMetadata, batches: list[pd.DataFrame]
    ) -> list[pd.DataFrame]: ...


class UploadStrategy:
    def upload(
        self,
        task: TaskMetadata,
        batches: list[pd.DataFrame],
        db: DatabaseBackend,
    ) -> int:
        count = 0
        with db.session_scope() as session:
            for df in batches:
                for _, row in df.iterrows():
                    thread = Thread(
                        unique_key=row["unique_key"],
                        etl_task_id=task.etl_task_id,
                        provider=row["provider"],
                        interaction_type=row["interaction_type"],
                        preview=row["preview"],
                        payload=row["payload"],
                        asset_uri=row.get("asset_uri"),
                        source=row.get("source"),
                        version=row["version"],
                        asat=row["asat"],
                    )
                    session.add(thread)
                    count += 1
        return count


class ETLPipeline:
    def __init__(
        self,
        extraction: ExtractionStrategy,
        transform: TransformStrategy,
        upload: UploadStrategy,
        storage: StorageBackend,
        db: DatabaseBackend,
    ) -> None:
        self._extraction = extraction
        self._transform = transform
        self._upload = upload
        self._storage = storage
        self._db = db

    def extract(self, task: TaskMetadata) -> list[pd.DataFrame]:
        try:
            return self._extraction.extract(task, self._storage)
        except Exception as exc:
            raise ExtractionFailedException(
                f"Extraction failed for task {task.etl_task_id}: {exc}"
            ) from exc

    def transform(
        self, task: TaskMetadata, batches: list[pd.DataFrame]
    ) -> list[pd.DataFrame]:
        try:
            return self._transform.transform(task, batches)
        except Exception as exc:
            raise TransformFailedException(
                f"Transform failed for task {task.etl_task_id}: {exc}"
            ) from exc

    def upload(
        self, task: TaskMetadata, batches: list[pd.DataFrame]
    ) -> int:
        try:
            return self._upload.upload(task, batches, self._db)
        except Exception as exc:
            raise UploadFailedException(
                f"Upload failed for task {task.etl_task_id}: {exc}"
            ) from exc

    def run(self, task: TaskMetadata) -> int:
        raw = self.extract(task)
        transformed = self.transform(task, raw)
        return self.upload(task, transformed)


import json
import struct
from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
from sqlite3 import Row
from typing import ClassVar

from context_use.models import (
    Archive,
    Batch,
    EtlTask,
    Facet,
    MemoryFacet,
    TapestryMemory,
    Thread,
)
from context_use.store.base import MemorySearchResult


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def now_utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


class BaseSqliteModel(ABC):
    table: ClassVar[str]

    @classmethod
    @abstractmethod
    def ddl(cls) -> str: ...

    @classmethod
    def indices(cls) -> list[str]:
        return []


class ArchiveRow(BaseSqliteModel):
    table = "archives"

    @classmethod
    def ddl(cls) -> str:
        return """\
CREATE TABLE IF NOT EXISTS archives (
    id          TEXT PRIMARY KEY,
    provider    TEXT NOT NULL,
    status      TEXT NOT NULL,
    file_uris   TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
)"""

    @classmethod
    def indices(cls) -> list[str]:
        return [
            "CREATE INDEX IF NOT EXISTS idx_archive_provider ON archives(provider)",
        ]

    @staticmethod
    def from_row(row: Row) -> Archive:
        return Archive(
            id=row["id"],
            provider=row["provider"],
            status=row["status"],
            file_uris=json.loads(row["file_uris"]) if row["file_uris"] else None,
            created_at=parse_dt(row["created_at"]),
            updated_at=parse_dt(row["updated_at"]),
        )


class EtlTaskRow(BaseSqliteModel):
    table = "etl_tasks"

    @classmethod
    def ddl(cls) -> str:
        return """\
CREATE TABLE IF NOT EXISTS etl_tasks (
    id                TEXT PRIMARY KEY,
    archive_id        TEXT NOT NULL REFERENCES archives(id),
    provider          TEXT NOT NULL,
    interaction_type  TEXT NOT NULL,
    source_uris       TEXT NOT NULL,
    status            TEXT NOT NULL,
    extracted_count   INTEGER NOT NULL DEFAULT 0,
    transformed_count INTEGER NOT NULL DEFAULT 0,
    uploaded_count    INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
)"""

    @classmethod
    def indices(cls) -> list[str]:
        return [
            "CREATE INDEX IF NOT EXISTS idx_task_archive ON etl_tasks(archive_id)",
        ]

    @staticmethod
    def from_row(row: Row) -> EtlTask:
        return EtlTask(
            id=row["id"],
            archive_id=row["archive_id"],
            provider=row["provider"],
            interaction_type=row["interaction_type"],
            source_uris=json.loads(row["source_uris"]),
            status=row["status"],
            extracted_count=row["extracted_count"],
            transformed_count=row["transformed_count"],
            uploaded_count=row["uploaded_count"],
            created_at=parse_dt(row["created_at"]),
            updated_at=parse_dt(row["updated_at"]),
        )


class ThreadRow(BaseSqliteModel):
    table = "threads"

    @classmethod
    def ddl(cls) -> str:
        return """\
CREATE TABLE IF NOT EXISTS threads (
    id                TEXT PRIMARY KEY,
    unique_key        TEXT NOT NULL UNIQUE,
    etl_task_id       TEXT REFERENCES etl_tasks(id),
    provider          TEXT NOT NULL,
    interaction_type  TEXT NOT NULL,
    preview           TEXT NOT NULL,
    payload           TEXT NOT NULL,
    asset_uri         TEXT,
    source            TEXT,
    version           TEXT NOT NULL,
    asat              TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
)"""

    @classmethod
    def indices(cls) -> list[str]:
        return [
            "CREATE INDEX IF NOT EXISTS idx_thread_key ON threads(unique_key)",
            "CREATE INDEX IF NOT EXISTS idx_thread_task ON threads(etl_task_id)",
            "CREATE INDEX IF NOT EXISTS idx_thread_provider ON threads(provider)",
            "CREATE INDEX IF NOT EXISTS idx_thread_type ON threads(interaction_type)",
            "CREATE INDEX IF NOT EXISTS idx_thread_asat ON threads(asat)",
        ]

    @staticmethod
    def from_row(row: Row) -> Thread:
        return Thread(
            id=row["id"],
            unique_key=row["unique_key"],
            etl_task_id=row["etl_task_id"],
            provider=row["provider"],
            interaction_type=row["interaction_type"],
            preview=row["preview"],
            payload=json.loads(row["payload"]),
            version=row["version"],
            asat=parse_dt(row["asat"]),
            asset_uri=row["asset_uri"],
            source=row["source"],
            created_at=parse_dt(row["created_at"]),
            updated_at=parse_dt(row["updated_at"]),
        )


class BatchRow(BaseSqliteModel):
    table = "batches"

    @classmethod
    def ddl(cls) -> str:
        return """\
CREATE TABLE IF NOT EXISTS batches (
    id            TEXT PRIMARY KEY,
    batch_number  INTEGER NOT NULL DEFAULT 1,
    category      TEXT NOT NULL,
    states        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
)"""

    @classmethod
    def indices(cls) -> list[str]:
        return [
            "CREATE INDEX IF NOT EXISTS idx_batch_category ON batches(category)",
        ]

    @staticmethod
    def from_row(row: Row) -> Batch:
        return Batch(
            id=row["id"],
            batch_number=row["batch_number"],
            category=row["category"],
            states=json.loads(row["states"]),
            created_at=parse_dt(row["created_at"]),
            updated_at=parse_dt(row["updated_at"]),
        )


class BatchThreadRow(BaseSqliteModel):
    table = "batch_threads"

    @classmethod
    def ddl(cls) -> str:
        return """\
CREATE TABLE IF NOT EXISTS batch_threads (
    id         TEXT PRIMARY KEY,
    batch_id   TEXT NOT NULL REFERENCES batches(id),
    thread_id  TEXT NOT NULL REFERENCES threads(id),
    group_id   TEXT NOT NULL
)"""

    @classmethod
    def indices(cls) -> list[str]:
        return [
            "CREATE INDEX IF NOT EXISTS idx_bt_batch ON batch_threads(batch_id)",
            "CREATE INDEX IF NOT EXISTS idx_bt_thread ON batch_threads(thread_id)",
            "CREATE INDEX IF NOT EXISTS idx_bt_group ON batch_threads(group_id)",
        ]


class MemoryRow(BaseSqliteModel):
    table = "tapestry_memories"

    @classmethod
    def ddl(cls) -> str:
        return """\
CREATE TABLE IF NOT EXISTS tapestry_memories (
    id                TEXT PRIMARY KEY,
    content           TEXT NOT NULL,
    from_date         TEXT NOT NULL,
    to_date           TEXT NOT NULL,
    group_id          TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'active',
    superseded_by     TEXT REFERENCES tapestry_memories(id),
    source_memory_ids TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
)"""

    @classmethod
    def indices(cls) -> list[str]:
        return [
            "CREATE INDEX IF NOT EXISTS idx_mem_from ON tapestry_memories(from_date)",
            "CREATE INDEX IF NOT EXISTS idx_mem_to ON tapestry_memories(to_date)",
            "CREATE INDEX IF NOT EXISTS idx_mem_group ON tapestry_memories(group_id)",
            "CREATE INDEX IF NOT EXISTS idx_mem_status ON tapestry_memories(status)",
        ]

    @staticmethod
    def from_row(row: Row) -> TapestryMemory:
        return TapestryMemory(
            id=row["id"],
            content=row["content"],
            from_date=_parse_date(row["from_date"]),
            to_date=_parse_date(row["to_date"]),
            group_id=row["group_id"],
            status=row["status"],
            superseded_by=row["superseded_by"],
            source_memory_ids=json.loads(row["source_memory_ids"])
            if row["source_memory_ids"]
            else None,
            created_at=parse_dt(row["created_at"]),
            updated_at=parse_dt(row["updated_at"]),
        )

    @staticmethod
    def to_search_result(
        row: Row,
        similarity: float | None,
    ) -> MemorySearchResult:
        return MemorySearchResult(
            id=row["id"],
            content=row["content"],
            from_date=_parse_date(row["from_date"]),
            to_date=_parse_date(row["to_date"]),
            similarity=similarity,
        )


class VecMemoryRow:
    table = "vec_memories"

    @classmethod
    def ddl(cls, embedding_dimensions: int) -> str:
        return (
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories "
            f"USING vec0(\n"
            f"    memory_id TEXT PRIMARY KEY,\n"
            f"    embedding float[{embedding_dimensions}] "
            f"distance_metric=cosine\n"
            f")"
        )

    @staticmethod
    def serialize(embedding: list[float]) -> bytes:
        from sqlite_vec import serialize_float32

        return serialize_float32(embedding)

    @staticmethod
    def deserialize(blob: bytes) -> list[float]:
        n = len(blob) // 4
        return list(struct.unpack(f"<{n}f", blob))


class FacetRow(BaseSqliteModel):
    table = "facets"

    @classmethod
    def ddl(cls) -> str:
        return """\
CREATE TABLE IF NOT EXISTS facets (
    id              TEXT PRIMARY KEY,
    facet_type      TEXT NOT NULL,
    facet_canonical TEXT NOT NULL,
    created_at      TEXT NOT NULL
)"""

    @classmethod
    def indices(cls) -> list[str]:
        return [
            "CREATE INDEX IF NOT EXISTS idx_facet_type ON facets(facet_type)",
        ]

    @staticmethod
    def from_row(row: Row) -> Facet:
        return Facet(
            id=row["id"],
            facet_type=row["facet_type"],
            facet_canonical=row["facet_canonical"],
            created_at=parse_dt(row["created_at"]),
        )


class MemoryFacetRow(BaseSqliteModel):
    table = "memory_facets"

    @classmethod
    def ddl(cls) -> str:
        return """\
CREATE TABLE IF NOT EXISTS memory_facets (
    id          TEXT PRIMARY KEY,
    memory_id   TEXT NOT NULL REFERENCES tapestry_memories(id),
    batch_id    TEXT REFERENCES batches(id),
    facet_type  TEXT NOT NULL,
    facet_value TEXT NOT NULL,
    facet_id    TEXT REFERENCES facets(id),
    created_at  TEXT NOT NULL
)"""

    @classmethod
    def indices(cls) -> list[str]:
        return [
            "CREATE INDEX IF NOT EXISTS idx_mfacet_memory ON memory_facets(memory_id)",
            "CREATE INDEX IF NOT EXISTS idx_mfacet_batch ON memory_facets(batch_id)",
            "CREATE INDEX IF NOT EXISTS idx_mfacet_linked ON memory_facets(facet_id)",
        ]

    @staticmethod
    def from_row(row: Row) -> MemoryFacet:
        return MemoryFacet(
            id=row["id"],
            memory_id=row["memory_id"],
            batch_id=row["batch_id"],
            facet_type=row["facet_type"],
            facet_value=row["facet_value"],
            facet_id=row["facet_id"],
            created_at=parse_dt(row["created_at"]),
        )


class VecFacetRow:
    table = "vec_facets"

    @classmethod
    def ddl(cls, embedding_dimensions: int) -> str:
        return (
            "CREATE VIRTUAL TABLE IF NOT EXISTS vec_facets "
            f"USING vec0(\n"
            f"    facet_id TEXT PRIMARY KEY,\n"
            f"    embedding float[{embedding_dimensions}] "
            f"distance_metric=cosine\n"
            f")"
        )

    @staticmethod
    def serialize(embedding: list[float]) -> bytes:
        from sqlite_vec import serialize_float32

        return serialize_float32(embedding)


_ALL_MODELS: list[type[BaseSqliteModel]] = [
    ArchiveRow,
    EtlTaskRow,
    ThreadRow,
    BatchRow,
    BatchThreadRow,
    MemoryRow,
    FacetRow,
    MemoryFacetRow,
]


def all_ddl_statements(embedding_dimensions: int) -> list[str]:
    stmts: list[str] = []
    for model in _ALL_MODELS:
        stmts.append(model.ddl())
        stmts.extend(model.indices())
    stmts.append(VecMemoryRow.ddl(embedding_dimensions))
    stmts.append(VecFacetRow.ddl(embedding_dimensions))
    return stmts

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime

import aiosqlite
import sqlite_vec

from context_use.batch.grouper import ThreadGroup
from context_use.etl.core.types import ThreadRow as EtlThreadRow
from context_use.models import (
    Archive,
    Batch,
    EtlTask,
    Facet,
    MemoryFacet,
    MemoryStatus,
    TapestryMemory,
    Thread,
)
from context_use.models.utils import generate_uuidv4
from context_use.store.base import MemorySearchResult, SortOrder, Store
from context_use.store.sqlite.schema import (
    ArchiveRow,
    BatchRow,
    EtlTaskRow,
    FacetRow,
    MemoryFacetRow,
    MemoryRow,
    ThreadRow,
    VecFacetRow,
    VecMemoryRow,
    all_ddl_statements,
    now_utc_iso,
    parse_dt,
)

logger = logging.getLogger(__name__)

BULK_INSERT_BATCH_SIZE = 500


class SqliteStore(Store):
    def __init__(self, path: str) -> None:
        self._path = path
        self._embedding_dimensions: int | None = None
        self._db: aiosqlite.Connection | None = None
        self._in_atomic = False
        self._atomic_lock = asyncio.Lock()

    async def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("SqliteStore not initialised — call init() first")
        return self._db

    async def _commit_unless_atomic(self) -> None:
        if not self._in_atomic:
            await (await self._conn()).commit()

    def _ensure_embedding_dimensions(self) -> int:
        if self._embedding_dimensions is None:
            raise RuntimeError("SqliteStore not initialized — call init() first")
        return self._embedding_dimensions

    async def init(self, *, embedding_dimensions: int) -> None:
        self._embedding_dimensions = embedding_dimensions
        conn = aiosqlite.connect(self._path)
        # Make sure that when the main thread exits,
        # the daemon thread is automatically killed
        conn._thread.daemon = True
        self._db = await conn
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")

        await self._db.enable_load_extension(True)
        await self._db.load_extension(sqlite_vec.loadable_path())
        await self._db.enable_load_extension(False)

        for stmt in all_ddl_statements(embedding_dimensions):
            await self._db.execute(stmt)
        await self._db.commit()
        await self._migrate(self._db)

    async def reset(self) -> None:
        dims = self._ensure_embedding_dimensions()
        db = await self._conn()
        await db.execute("PRAGMA foreign_keys=OFF")
        rows = await db.execute_fetchall(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table', 'index') "
            "AND name NOT LIKE 'sqlite_%'"
        )
        for name, obj_type in rows:
            if obj_type == "table":
                await db.execute(f"DROP TABLE IF EXISTS [{name}]")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.commit()

        for stmt in all_ddl_statements(dims):
            await db.execute(stmt)
        await db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @asynccontextmanager
    async def atomic(self) -> AsyncIterator[None]:
        async with self._atomic_lock:
            db = await self._conn()
            self._in_atomic = True
            await db.execute("BEGIN")
            try:
                yield
                await db.commit()
            except Exception:
                await db.rollback()
                raise
            finally:
                self._in_atomic = False

    async def create_archive(
        self,
        archive: Archive,
    ) -> Archive:
        db = await self._conn()
        now = now_utc_iso()
        archive.created_at = parse_dt(now)
        archive.updated_at = parse_dt(now)
        await db.execute(
            "INSERT INTO archives "
            "(id, provider, status, file_uris, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                archive.id,
                archive.provider,
                archive.status,
                json.dumps(archive.file_uris)
                if archive.file_uris is not None
                else None,
                now,
                now,
            ),
        )
        await self._commit_unless_atomic()
        return archive

    async def get_archive(
        self,
        archive_id: str,
    ) -> Archive | None:
        db = await self._conn()
        rows = list(
            await db.execute_fetchall(
                "SELECT * FROM archives WHERE id = ?",
                (archive_id,),
            )
        )
        if not rows:
            return None
        return ArchiveRow.from_row(rows[0])

    async def update_archive(
        self,
        archive: Archive,
    ) -> None:
        db = await self._conn()
        now = now_utc_iso()
        archive.updated_at = parse_dt(now)
        await db.execute(
            "UPDATE archives "
            "SET status = ?, file_uris = ?, updated_at = ? "
            "WHERE id = ?",
            (
                archive.status,
                json.dumps(archive.file_uris)
                if archive.file_uris is not None
                else None,
                now,
                archive.id,
            ),
        )
        await self._commit_unless_atomic()

    async def create_task(self, task: EtlTask) -> EtlTask:
        db = await self._conn()
        now = now_utc_iso()
        task.created_at = parse_dt(now)
        task.updated_at = parse_dt(now)
        await db.execute(
            "INSERT INTO etl_tasks "
            "(id, archive_id, provider, interaction_type, "
            "source_uris, status, extracted_count, "
            "transformed_count, uploaded_count, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task.id,
                task.archive_id,
                task.provider,
                task.interaction_type,
                json.dumps(task.source_uris),
                task.status,
                task.extracted_count,
                task.transformed_count,
                task.uploaded_count,
                now,
                now,
            ),
        )
        await self._commit_unless_atomic()
        return task

    async def get_task(
        self,
        task_id: str,
    ) -> EtlTask | None:
        db = await self._conn()
        rows = list(
            await db.execute_fetchall(
                "SELECT * FROM etl_tasks WHERE id = ?",
                (task_id,),
            )
        )
        if not rows:
            return None
        return EtlTaskRow.from_row(rows[0])

    async def update_task(self, task: EtlTask) -> None:
        db = await self._conn()
        now = now_utc_iso()
        task.updated_at = parse_dt(now)
        await db.execute(
            "UPDATE etl_tasks "
            "SET status = ?, extracted_count = ?, "
            "transformed_count = ?, uploaded_count = ?, "
            "updated_at = ? "
            "WHERE id = ?",
            (
                task.status,
                task.extracted_count,
                task.transformed_count,
                task.uploaded_count,
                now,
                task.id,
            ),
        )
        await self._commit_unless_atomic()

    _THREAD_INSERT = (
        "INSERT OR IGNORE INTO threads "
        "(id, unique_key, etl_task_id, provider, "
        "interaction_type, preview, payload, content, asset_uri, "
        "source, collection_id, version, asat, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )

    async def insert_threads(
        self,
        rows: list[EtlThreadRow],
        task_id: str | None = None,
    ) -> list[str]:
        if not rows:
            return []
        db = await self._conn()
        now = now_utc_iso()
        inserted_ids: list[str] = []

        batch: list[tuple] = []
        for row in rows:
            batch.append(
                (
                    generate_uuidv4(),
                    row.unique_key,
                    task_id,
                    row.provider,
                    row.interaction_type,
                    row.preview,
                    json.dumps(row.payload),
                    None,
                    row.asset_uri,
                    row.source,
                    row.collection_id,
                    row.version,
                    row.asat.isoformat(),
                    now,
                    now,
                )
            )
            if len(batch) >= BULK_INSERT_BATCH_SIZE:
                inserted_ids.extend(await self._flush_thread_batch(db, batch))
                batch = []
        if batch:
            inserted_ids.extend(await self._flush_thread_batch(db, batch))

        await self._commit_unless_atomic()
        return inserted_ids

    async def get_unprocessed_threads(
        self,
        *,
        batch_category: str | None = None,
        interaction_types: list[str] | None = None,
        since: datetime | None = None,
        before: datetime | None = None,
    ) -> list[Thread]:
        db = await self._conn()
        params: list = []

        if batch_category is not None:
            sql = (
                "SELECT t.* FROM threads t "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM batch_threads bt"
                "  JOIN batches b ON bt.batch_id = b.id"
                "  WHERE bt.thread_id = t.id AND b.category = ?"
                ")"
            )
            params.append(batch_category)
        else:
            sql = (
                "SELECT t.* FROM threads t "
                "LEFT JOIN batch_threads bt ON bt.thread_id = t.id "
                "WHERE bt.thread_id IS NULL"
            )

        if interaction_types is not None:
            ph = ",".join("?" for _ in interaction_types)
            sql += f" AND t.interaction_type IN ({ph})"
            params.extend(interaction_types)
        if since is not None:
            sql += " AND t.asat >= ?"
            params.append(since.isoformat())
        if before is not None:
            sql += " AND t.asat < ?"
            params.append(before.isoformat())
        sql += " ORDER BY t.asat, t.id"

        rows = await db.execute_fetchall(sql, params)
        return [ThreadRow.from_row(r) for r in rows]

    async def update_thread_content(self, thread_id: str, content: str) -> None:
        db = await self._conn()
        now = now_utc_iso()
        await db.execute(
            "UPDATE threads SET content = ?, updated_at = ? WHERE id = ?",
            (content, now, thread_id),
        )
        await self._commit_unless_atomic()

    async def list_threads_by_ids(self, ids: list[str]) -> list[Thread]:
        if not ids:
            return []
        db = await self._conn()
        ph = ",".join("?" for _ in ids)
        rows = await db.execute_fetchall(
            f"SELECT * FROM threads WHERE id IN ({ph})", ids
        )
        return [ThreadRow.from_row(r) for r in rows]

    async def list_threads(
        self,
        *,
        collection_id: str | None = None,
        interaction_type: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int | None = None,
        asat_order: SortOrder = SortOrder.ASC,
    ) -> list[Thread]:
        db = await self._conn()
        sql = "SELECT * FROM threads WHERE 1=1"
        params: list = []
        if collection_id is not None:
            sql += " AND collection_id = ?"
            params.append(collection_id)
        if interaction_type is not None:
            sql += " AND interaction_type = ?"
            params.append(interaction_type)
        if from_date is not None:
            sql += " AND asat >= ?"
            params.append(from_date.isoformat())
        if to_date is not None:
            sql += " AND asat < ?"
            params.append(to_date.isoformat())
        if asat_order == SortOrder.ASC:
            sql += " ORDER BY asat, id"
        else:
            sql += " ORDER BY asat DESC, id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = await db.execute_fetchall(sql, params)
        return [ThreadRow.from_row(r) for r in rows]

    async def create_batch(
        self,
        batch: Batch,
        groups: list[ThreadGroup],
    ) -> Batch:
        db = await self._conn()
        now = now_utc_iso()
        batch.created_at = parse_dt(now)
        batch.updated_at = parse_dt(now)
        await db.execute(
            "INSERT INTO batches "
            "(id, batch_number, category, states, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                batch.id,
                batch.batch_number,
                batch.category,
                json.dumps(batch.states),
                now,
                now,
            ),
        )
        for grp in groups:
            for thread in grp.threads:
                await db.execute(
                    "INSERT INTO batch_threads "
                    "(id, batch_id, thread_id, group_id) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        generate_uuidv4(),
                        batch.id,
                        thread.id,
                        grp.group_id,
                    ),
                )
        await self._commit_unless_atomic()
        return batch

    async def get_batch(
        self,
        batch_id: str,
    ) -> Batch | None:
        db = await self._conn()
        rows = list(
            await db.execute_fetchall(
                "SELECT * FROM batches WHERE id = ?",
                (batch_id,),
            )
        )
        if not rows:
            return None
        return BatchRow.from_row(rows[0])

    async def update_batch(self, batch: Batch) -> None:
        db = await self._conn()
        now = now_utc_iso()
        batch.updated_at = parse_dt(now)
        await db.execute(
            "UPDATE batches SET states = ?, updated_at = ? WHERE id = ?",
            (json.dumps(batch.states), now, batch.id),
        )
        await self._commit_unless_atomic()

    async def get_batch_groups(
        self,
        batch_id: str,
    ) -> list[ThreadGroup]:
        db = await self._conn()
        rows = await db.execute_fetchall(
            "SELECT bt.group_id, t.* "
            "FROM batch_threads bt "
            "JOIN threads t ON bt.thread_id = t.id "
            "WHERE bt.batch_id = ? "
            "ORDER BY bt.group_id, t.asat",
            (batch_id,),
        )
        groups_map: dict[str, list[Thread]] = defaultdict(list)
        for r in rows:
            groups_map[r["group_id"]].append(ThreadRow.from_row(r))
        return [
            ThreadGroup(threads=threads, group_id=gid)
            for gid, threads in groups_map.items()
            if threads
        ]

    async def create_memory(
        self,
        memory: TapestryMemory,
    ) -> TapestryMemory:
        db = await self._conn()
        now = now_utc_iso()
        memory.created_at = parse_dt(now)
        memory.updated_at = parse_dt(now)
        await db.execute(
            "INSERT INTO tapestry_memories "
            "(id, content, from_date, to_date, group_id, "
            "status, superseded_by, source_memory_ids, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                memory.id,
                memory.content,
                memory.from_date.isoformat(),
                memory.to_date.isoformat(),
                memory.group_id,
                memory.status,
                memory.superseded_by,
                json.dumps(memory.source_memory_ids)
                if memory.source_memory_ids
                else None,
                now,
                now,
            ),
        )
        if memory.embedding is not None:
            await _upsert_embedding(db, memory)
        await self._commit_unless_atomic()
        return memory

    async def get_memories(
        self,
        ids: list[str],
    ) -> list[TapestryMemory]:
        if not ids:
            return []
        db = await self._conn()
        ph = ",".join("?" for _ in ids)
        rows = await db.execute_fetchall(
            f"SELECT * FROM tapestry_memories WHERE id IN ({ph})",
            ids,
        )
        memories = [MemoryRow.from_row(r) for r in rows]
        await _load_embeddings(db, memories)
        return memories

    async def get_unembedded_memories(
        self,
        ids: list[str],
    ) -> list[TapestryMemory]:
        if not ids:
            return []
        db = await self._conn()
        ph = ",".join("?" for _ in ids)
        rows = await db.execute_fetchall(
            "SELECT m.* FROM tapestry_memories m "
            "LEFT JOIN vec_memories v "
            "ON v.memory_id = m.id "
            f"WHERE m.id IN ({ph}) "
            "AND v.memory_id IS NULL",
            ids,
        )
        return [MemoryRow.from_row(r) for r in rows]

    async def update_memory(
        self,
        memory: TapestryMemory,
    ) -> None:
        db = await self._conn()
        now = now_utc_iso()
        memory.updated_at = parse_dt(now)
        await db.execute(
            "UPDATE tapestry_memories "
            "SET content = ?, from_date = ?, to_date = ?, "
            "status = ?, superseded_by = ?, "
            "source_memory_ids = ?, updated_at = ? "
            "WHERE id = ?",
            (
                memory.content,
                memory.from_date.isoformat(),
                memory.to_date.isoformat(),
                memory.status,
                memory.superseded_by,
                json.dumps(memory.source_memory_ids)
                if memory.source_memory_ids
                else None,
                now,
                memory.id,
            ),
        )
        if memory.embedding is not None:
            await _upsert_embedding(db, memory)
        await self._commit_unless_atomic()

    async def list_memories(
        self,
        *,
        status: str | None = None,
        from_date: date | None = None,
        limit: int | None = None,
    ) -> list[TapestryMemory]:
        db = await self._conn()
        sql = "SELECT * FROM tapestry_memories"
        clauses: list[str] = []
        params: list = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if from_date is not None:
            clauses.append("from_date >= ?")
            params.append(from_date.isoformat())
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY from_date"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        rows = await db.execute_fetchall(sql, params)
        memories = [MemoryRow.from_row(r) for r in rows]
        await _load_embeddings(db, memories)
        return memories

    async def count_memories(
        self,
        *,
        status: str | None = None,
    ) -> int:
        db = await self._conn()
        if status is not None:
            sql = "SELECT COUNT(*) FROM tapestry_memories WHERE status = ?"
            params: list = [status]
        else:
            sql = "SELECT COUNT(*) FROM tapestry_memories"
            params = []
        rows = list(await db.execute_fetchall(sql, params))
        return rows[0][0]

    async def search_memories(
        self,
        *,
        query_embedding: list[float],
        from_date: date | None = None,
        to_date: date | None = None,
        top_k: int = 5,
    ) -> list[MemorySearchResult]:
        db = await self._conn()
        return await _search_by_embedding(
            db,
            query_embedding,
            from_date=from_date,
            to_date=to_date,
            top_k=top_k,
        )

    async def create_memory_facet(self, facet: MemoryFacet) -> MemoryFacet:
        db = await self._conn()
        await db.execute(
            "INSERT INTO memory_facets "
            "(id, memory_id, batch_id, facet_type, facet_value, facet_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                facet.id,
                facet.memory_id,
                facet.batch_id,
                facet.facet_type,
                facet.facet_value,
                facet.facet_id,
                facet.created_at.isoformat(),
            ),
        )
        await self._commit_unless_atomic()
        return facet

    async def get_unembedded_memory_facets(
        self, *, batch_id: str | None = None
    ) -> list[MemoryFacet]:
        db = await self._conn()
        sql = (
            "SELECT mf.* FROM memory_facets mf "
            "LEFT JOIN vec_facets vf ON vf.facet_id = mf.id "
            "WHERE vf.facet_id IS NULL"
        )
        params: list = []
        if batch_id is not None:
            sql += " AND mf.batch_id = ?"
            params.append(batch_id)
        rows = await db.execute_fetchall(sql, params)
        return [MemoryFacetRow.from_row(r) for r in rows]

    async def update_memory_facet(self, facet: MemoryFacet) -> None:
        db = await self._conn()
        await db.execute(
            "UPDATE memory_facets SET facet_id = ? WHERE id = ?",
            (facet.facet_id, facet.id),
        )
        await self._commit_unless_atomic()

    async def get_unlinked_memory_facets(self) -> list[MemoryFacet]:
        db = await self._conn()
        rows = await db.execute_fetchall(
            "SELECT mf.* FROM memory_facets mf "
            "JOIN vec_facets vf ON vf.facet_id = mf.id "
            "WHERE mf.facet_id IS NULL"
        )
        facets = [MemoryFacetRow.from_row(r) for r in rows]
        await _load_facet_embeddings(db, facets)
        return facets

    async def create_facet(self, facet: Facet) -> Facet:
        db = await self._conn()
        await db.execute(
            "INSERT INTO facets (id, facet_type, facet_canonical, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                facet.id,
                facet.facet_type,
                facet.facet_canonical,
                facet.created_at.isoformat(),
            ),
        )
        await self._commit_unless_atomic()
        return facet

    async def create_facet_embedding(
        self, facet_id: str, embedding: list[float]
    ) -> None:
        db = await self._conn()
        await db.execute(
            "DELETE FROM vec_facets WHERE facet_id = ?",
            (facet_id,),
        )
        await db.execute(
            "INSERT INTO vec_facets (facet_id, embedding) VALUES (?, ?)",
            (facet_id, VecFacetRow.serialize(embedding)),
        )
        await self._commit_unless_atomic()

    async def find_similar_facet(
        self,
        facet_type: str,
        embedding: list[float],
        threshold: float,
    ) -> Facet | None:
        db = await self._conn()
        vec_rows = await db.execute_fetchall(
            "SELECT facet_id, distance FROM vec_facets "
            "WHERE embedding MATCH ? AND k = ?",
            (VecFacetRow.serialize(embedding), 10),
        )
        if not vec_rows:
            return None

        max_distance = 1.0 - threshold
        candidate_ids = [r[0] for r in vec_rows if r[1] <= max_distance]
        if not candidate_ids:
            return None

        distances: dict[str, float] = {r[0]: r[1] for r in vec_rows}

        ph = ",".join("?" for _ in candidate_ids)
        rows = await db.execute_fetchall(
            f"SELECT * FROM facets WHERE id IN ({ph}) AND facet_type = ?",
            [*candidate_ids, facet_type],
        )
        if not rows:
            return None

        best = min(rows, key=lambda r: distances.get(r["id"], 1.0))
        return FacetRow.from_row(best)

    @staticmethod
    async def _migrate(db: aiosqlite.Connection) -> None:
        cursor = await db.execute("PRAGMA table_info(threads)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "content" not in columns:
            await db.execute("ALTER TABLE threads ADD COLUMN content TEXT")
            await db.commit()

    @classmethod
    async def _flush_thread_batch(
        cls,
        db: aiosqlite.Connection,
        batch: list[tuple],
    ) -> list[str]:
        candidate_ids: list[str] = [row[0] for row in batch]
        await db.executemany(cls._THREAD_INSERT, batch)
        ph = ",".join("?" for _ in candidate_ids)
        rows = list(
            await db.execute_fetchall(
                f"SELECT id FROM threads WHERE id IN ({ph})",
                candidate_ids,
            )
        )
        return [row[0] for row in rows]


async def _upsert_embedding(
    db: aiosqlite.Connection,
    memory: TapestryMemory,
) -> None:
    assert memory.embedding is not None
    # sqlite-vec virtual tables don't honour INSERT OR REPLACE conflict
    # resolution, raising a UNIQUE constraint error instead of replacing the
    # existing row. Use DELETE + INSERT to achieve the same semantics.
    await db.execute(
        "DELETE FROM vec_memories WHERE memory_id = ?",
        (memory.id,),
    )
    await db.execute(
        "INSERT INTO vec_memories (memory_id, embedding) VALUES (?, ?)",
        (
            memory.id,
            VecMemoryRow.serialize(memory.embedding),
        ),
    )


async def _load_embeddings(
    db: aiosqlite.Connection,
    memories: list[TapestryMemory],
) -> None:
    if not memories:
        return
    ids = [m.id for m in memories]
    ph = ",".join("?" for _ in ids)
    rows = await db.execute_fetchall(
        f"SELECT memory_id, embedding FROM vec_memories WHERE memory_id IN ({ph})",
        ids,
    )
    emb_map: dict[str, list[float]] = {
        r[0]: VecMemoryRow.deserialize(r[1]) for r in rows
    }
    for m in memories:
        m.embedding = emb_map.get(m.id)


async def _search_by_embedding(
    db: aiosqlite.Connection,
    query_embedding: list[float],
    *,
    from_date: date | None,
    to_date: date | None,
    top_k: int,
) -> list[MemorySearchResult]:
    vec_rows = await db.execute_fetchall(
        "SELECT memory_id, distance FROM vec_memories "
        "WHERE embedding MATCH ? AND k = ?",
        (
            VecMemoryRow.serialize(query_embedding),
            top_k * 4,
        ),
    )
    if not vec_rows:
        return []

    candidate_ids = [r[0] for r in vec_rows]
    distances: dict = {r[0]: r[1] for r in vec_rows}

    ph = ",".join("?" for _ in candidate_ids)
    sql = (
        "SELECT id, content, from_date, to_date "
        "FROM tapestry_memories "
        f"WHERE id IN ({ph}) AND status = ?"
    )
    params: list = [*candidate_ids, MemoryStatus.active.value]
    if from_date is not None:
        sql += " AND from_date >= ?"
        params.append(from_date.isoformat())
    if to_date is not None:
        sql += " AND to_date <= ?"
        params.append(to_date.isoformat())

    mem_rows = await db.execute_fetchall(sql, params)

    results = [
        MemoryRow.to_search_result(
            r,
            1.0 - distances[r["id"]],
        )
        for r in mem_rows
        if r["id"] in distances
    ]
    results.sort(
        key=lambda x: x.similarity or 0.0,
        reverse=True,
    )
    return results[:top_k]


async def _load_facet_embeddings(
    db: aiosqlite.Connection,
    facets: list[MemoryFacet],
) -> None:
    if not facets:
        return
    ids = [f.id for f in facets]
    ph = ",".join("?" for _ in ids)
    rows = await db.execute_fetchall(
        f"SELECT facet_id, embedding FROM vec_facets WHERE facet_id IN ({ph})",
        ids,
    )
    emb_map: dict[str, list[float]] = {
        r[0]: VecMemoryRow.deserialize(r[1]) for r in rows
    }
    for f in facets:
        f.embedding = emb_map.get(f.id)

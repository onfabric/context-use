from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

import aiosqlite
import sqlite_vec

from context_use.batch.grouper import ThreadGroup
from context_use.etl.core.types import ThreadRow as EtlThreadRow
from context_use.models import (
    Archive,
    Batch,
    EtlTask,
    MemoryStatus,
    TapestryMemory,
    Thread,
)
from context_use.models.utils import generate_uuidv4
from context_use.store.base import MemorySearchResult, Store
from context_use.store.sqlite.schema import (
    ArchiveRow,
    BatchRow,
    EtlTaskRow,
    MemoryRow,
    ThreadRow,
    VecMemoryRow,
    all_ddl_statements,
    now_utc_iso,
    parse_dt,
)

logger = logging.getLogger(__name__)

BULK_INSERT_BATCH_SIZE = 500


class SqliteStore(Store):
    def __init__(self, path: str = "context_use.db") -> None:
        self._path = path
        self._db: aiosqlite.Connection | None = None
        self._in_atomic = False

    async def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("SqliteStore not initialised — call init() first")
        return self._db

    async def _commit_unless_atomic(self) -> None:
        if not self._in_atomic:
            await (await self._conn()).commit()

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")

        await self._db.enable_load_extension(True)
        await self._db.load_extension(sqlite_vec.loadable_path())
        await self._db.enable_load_extension(False)

        for stmt in all_ddl_statements():
            await self._db.execute(stmt)
        await self._db.commit()

    async def reset(self) -> None:
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

        for stmt in all_ddl_statements():
            await db.execute(stmt)
        await db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @asynccontextmanager
    async def atomic(self) -> AsyncIterator[None]:
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
        "interaction_type, preview, payload, asset_uri, "
        "source, version, asat, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )

    async def insert_threads(
        self,
        rows: list[EtlThreadRow],
        task_id: str,
    ) -> int:
        if not rows:
            return 0
        db = await self._conn()
        now = now_utc_iso()
        total = 0

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
                    row.asset_uri,
                    row.source,
                    row.version,
                    row.asat.isoformat(),
                    now,
                    now,
                )
            )
            if len(batch) >= BULK_INSERT_BATCH_SIZE:
                total += await self._flush_thread_batch(
                    db,
                    batch,
                )
                batch = []
        if batch:
            total += await self._flush_thread_batch(
                db,
                batch,
            )

        await self._commit_unless_atomic()
        return total

    async def get_unprocessed_threads(
        self,
        *,
        interaction_types: list[str] | None = None,
    ) -> list[Thread]:
        db = await self._conn()
        sql = (
            "SELECT t.* FROM threads t "
            "LEFT JOIN batch_threads bt "
            "ON bt.thread_id = t.id "
            "WHERE bt.thread_id IS NULL"
        )
        params: list = []
        if interaction_types is not None:
            ph = ",".join("?" for _ in interaction_types)
            sql += f" AND t.interaction_type IN ({ph})"
            params.extend(interaction_types)
        sql += " ORDER BY t.asat, t.id"

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
        query_embedding: list[float] | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        top_k: int = 5,
    ) -> list[MemorySearchResult]:
        db = await self._conn()

        if query_embedding is not None:
            return await _search_by_embedding(
                db,
                query_embedding,
                from_date=from_date,
                to_date=to_date,
                top_k=top_k,
            )

        return await _search_by_date(
            db,
            from_date=from_date,
            to_date=to_date,
            top_k=top_k,
        )

    @classmethod
    async def _flush_thread_batch(
        cls,
        db: aiosqlite.Connection,
        batch: list[tuple],
    ) -> int:
        rows = list(await db.execute_fetchall("SELECT COUNT(*) FROM threads"))
        before = rows[0][0]
        await db.executemany(cls._THREAD_INSERT, batch)
        rows = list(await db.execute_fetchall("SELECT COUNT(*) FROM threads"))
        return rows[0][0] - before


async def _upsert_embedding(
    db: aiosqlite.Connection,
    memory: TapestryMemory,
) -> None:
    assert memory.embedding is not None
    await db.execute(
        "INSERT OR REPLACE INTO vec_memories (memory_id, embedding) VALUES (?, ?)",
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


async def _search_by_date(
    db: aiosqlite.Connection,
    *,
    from_date: date | None,
    to_date: date | None,
    top_k: int,
) -> list[MemorySearchResult]:
    sql = (
        "SELECT id, content, from_date, to_date FROM tapestry_memories WHERE status = ?"
    )
    params: list = [MemoryStatus.active.value]
    if from_date is not None:
        sql += " AND from_date >= ?"
        params.append(from_date.isoformat())
    if to_date is not None:
        sql += " AND to_date <= ?"
        params.append(to_date.isoformat())
    sql += " ORDER BY from_date DESC LIMIT ?"
    params.append(top_k)

    rows = await db.execute_fetchall(sql, params)
    return [MemoryRow.to_search_result(r, None) for r in rows]

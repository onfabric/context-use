from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

from sqlalchemy import and_, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql import text

from context_use.batch.grouper import ThreadGroup
from context_use.batch.models import Batch as OrmBatch
from context_use.batch.models import BatchThread as OrmBatchThread
from context_use.db.models import Base
from context_use.etl.core.types import ThreadRow
from context_use.etl.models.archive import Archive as OrmArchive
from context_use.etl.models.etl_task import EtlTask as OrmEtlTask
from context_use.etl.models.thread import Thread as OrmThread
from context_use.memories.models import TapestryMemory as OrmMemory
from context_use.models import (
    Archive,
    Batch,
    EtlTask,
    MemoryStatus,
    TapestryMemory,
    TapestryProfile,
    Thread,
)
from context_use.profile.models import TapestryProfile as OrmProfile
from context_use.store.base import MemorySearchResult, Store

logger = logging.getLogger(__name__)

BULK_INSERT_BATCH_SIZE = 500


class PostgresStore(Store):
    """Store backed by PostgreSQL via SQLAlchemy + asyncpg.

    Wraps the existing ORM models and translates to/from domain
    dataclasses at the boundary.
    """

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        *,
        pool_size: int = 10,
        max_overflow: int = 20,
    ) -> None:
        url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
        self._engine = create_async_engine(
            url,
            echo=False,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._scoped_session: AsyncSession | None = None

    def _session(self) -> AsyncSession:
        """Return the scoped session (inside ``atomic()``) or a new one."""
        if self._scoped_session is not None:
            return self._scoped_session
        return self._session_factory()

    @asynccontextmanager
    async def _auto_session(self) -> AsyncIterator[AsyncSession]:
        """Yield the scoped session if inside ``atomic()``, else a fresh
        auto-committing session that is closed after use."""
        if self._scoped_session is not None:
            yield self._scoped_session
            return
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    # ── Lifecycle ────────────────────────────────────────────────────

    async def init(self) -> None:
        self._register_models()
        async with self._engine.begin() as conn:
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS public"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)

    async def reset(self) -> None:
        self._register_models()
        async with self._engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
        await self.init()

    async def close(self) -> None:
        await self._engine.dispose()

    @asynccontextmanager
    async def atomic(self) -> AsyncIterator[None]:
        session = self._session_factory()
        self._scoped_session = session
        try:
            yield
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
            self._scoped_session = None

    @staticmethod
    def _register_models() -> None:
        import context_use.batch.models  # noqa: F401
        import context_use.etl.models  # noqa: F401
        import context_use.memories.models  # noqa: F401
        import context_use.profile.models  # noqa: F401

    # ── Archives ─────────────────────────────────────────────────────

    async def create_archive(self, archive: Archive) -> Archive:
        async with self._auto_session() as s:
            row = OrmArchive(
                id=archive.id,
                provider=archive.provider,
                status=archive.status,
                file_uris=archive.file_uris,
            )
            s.add(row)
            await s.flush()
            archive.created_at = row.created_at
            archive.updated_at = row.updated_at
        return archive

    async def get_archive(self, archive_id: str) -> Archive | None:
        async with self._auto_session() as s:
            row = await s.get(OrmArchive, archive_id)
        if row is None:
            return None
        return _archive_from_orm(row)

    async def update_archive(self, archive: Archive) -> None:
        async with self._auto_session() as s:
            row = await s.get(OrmArchive, archive.id)
            if row is None:
                raise ValueError(f"Archive {archive.id} not found")
            row.status = archive.status
            row.file_uris = archive.file_uris

    async def list_archives(self, *, status: str | None = None) -> list[Archive]:
        async with self._auto_session() as s:
            stmt = select(OrmArchive).order_by(OrmArchive.created_at)
            if status is not None:
                stmt = stmt.where(OrmArchive.status == status)
            rows = list((await s.execute(stmt)).scalars().all())
        return [_archive_from_orm(r) for r in rows]

    async def count_threads_for_archive(self, archive_id: str) -> int:
        async with self._auto_session() as s:
            stmt = (
                select(func.count(OrmThread.id))
                .join(OrmEtlTask, OrmThread.etl_task_id == OrmEtlTask.id)
                .where(OrmEtlTask.archive_id == archive_id)
            )
            return (await s.execute(stmt)).scalar() or 0

    # ── ETL Tasks ────────────────────────────────────────────────────

    async def create_task(self, task: EtlTask) -> EtlTask:
        async with self._auto_session() as s:
            row = OrmEtlTask(
                id=task.id,
                archive_id=task.archive_id,
                provider=task.provider,
                interaction_type=task.interaction_type,
                source_uri=task.source_uri,
                status=task.status,
                extracted_count=task.extracted_count,
                transformed_count=task.transformed_count,
                uploaded_count=task.uploaded_count,
            )
            s.add(row)
            await s.flush()
            task.created_at = row.created_at
            task.updated_at = row.updated_at
        return task

    async def get_task(self, task_id: str) -> EtlTask | None:
        async with self._auto_session() as s:
            row = await s.get(OrmEtlTask, task_id)
        if row is None:
            return None
        return _task_from_orm(row)

    async def update_task(self, task: EtlTask) -> None:
        async with self._auto_session() as s:
            row = await s.get(OrmEtlTask, task.id)
            if row is None:
                raise ValueError(f"EtlTask {task.id} not found")
            row.status = task.status
            row.extracted_count = task.extracted_count
            row.transformed_count = task.transformed_count
            row.uploaded_count = task.uploaded_count

    async def get_tasks_by_archive(self, archive_ids: list[str]) -> list[EtlTask]:
        async with self._auto_session() as s:
            stmt = select(OrmEtlTask).where(OrmEtlTask.archive_id.in_(archive_ids))
            rows = list((await s.execute(stmt)).scalars().all())
        return [_task_from_orm(r) for r in rows]

    # ── Threads ──────────────────────────────────────────────────────

    async def insert_threads(self, rows: list[ThreadRow], task_id: str) -> int:
        if not rows:
            return 0
        total = 0
        async with self._auto_session() as s:
            batch: list[dict] = []
            for row in rows:
                batch.append(
                    {
                        "unique_key": row.unique_key,
                        "etl_task_id": task_id,
                        "provider": row.provider,
                        "interaction_type": row.interaction_type,
                        "preview": row.preview,
                        "payload": row.payload,
                        "source": row.source,
                        "version": row.version,
                        "asat": row.asat,
                        "asset_uri": row.asset_uri,
                    }
                )
                if len(batch) >= BULK_INSERT_BATCH_SIZE:
                    total += await _flush_thread_batch(s, batch)
                    batch = []
            if batch:
                total += await _flush_thread_batch(s, batch)
        return total

    async def get_threads_by_task(self, task_ids: list[str]) -> list[Thread]:
        async with self._auto_session() as s:
            stmt = (
                select(OrmThread)
                .where(OrmThread.etl_task_id.in_(task_ids))
                .order_by(OrmThread.asat, OrmThread.id)
            )
            rows = list((await s.execute(stmt)).scalars().all())
        return [_thread_from_orm(r) for r in rows]

    # ── Batches ──────────────────────────────────────────────────────

    async def create_batch(self, batch: Batch, groups: list[ThreadGroup]) -> Batch:
        async with self._auto_session() as s:
            row = OrmBatch(
                id=batch.id,
                batch_number=batch.batch_number,
                category=batch.category,
                states=batch.states,
            )
            s.add(row)
            await s.flush()

            for grp in groups:
                for thread in grp.threads:
                    s.add(
                        OrmBatchThread(
                            batch_id=batch.id,
                            thread_id=thread.id,
                            group_id=grp.group_id,
                        )
                    )
            await s.flush()
            batch.created_at = row.created_at
            batch.updated_at = row.updated_at
        return batch

    async def get_batch(self, batch_id: str) -> Batch | None:
        async with self._auto_session() as s:
            row = await s.get(OrmBatch, batch_id)
        if row is None:
            return None
        return _batch_from_orm(row)

    async def update_batch(self, batch: Batch) -> None:
        async with self._auto_session() as s:
            row = await s.get(OrmBatch, batch.id)
            if row is None:
                raise ValueError(f"Batch {batch.id} not found")
            row.states = batch.states
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(row, "states")

    async def get_batch_groups(self, batch_id: str) -> list[ThreadGroup]:
        async with self._auto_session() as s:
            stmt = (
                select(OrmBatchThread.group_id, OrmThread)
                .join(OrmThread, OrmBatchThread.thread_id == OrmThread.id)
                .where(OrmBatchThread.batch_id == batch_id)
                .order_by(OrmBatchThread.group_id, OrmThread.asat)
            )
            rows = (await s.execute(stmt)).all()

        groups_map: dict[str, list[Thread]] = defaultdict(list)
        for group_id, orm_thread in rows:
            groups_map[group_id].append(_thread_from_orm(orm_thread))

        return [
            ThreadGroup(
                threads=threads,  # type: ignore[arg-type]
                group_id=gid,
            )
            for gid, threads in groups_map.items()
        ]

    # ── Memories ─────────────────────────────────────────────────────

    async def create_memory(self, memory: TapestryMemory) -> TapestryMemory:
        async with self._auto_session() as s:
            row = OrmMemory(
                id=memory.id,
                content=memory.content,
                from_date=memory.from_date,
                to_date=memory.to_date,
                group_id=memory.group_id,
                embedding=memory.embedding,
                status=memory.status,
                superseded_by=memory.superseded_by,
                source_memory_ids=memory.source_memory_ids,
            )
            s.add(row)
            await s.flush()
            memory.created_at = row.created_at
            memory.updated_at = row.updated_at
        return memory

    async def get_memories(self, ids: list[str]) -> list[TapestryMemory]:
        if not ids:
            return []
        async with self._auto_session() as s:
            stmt = select(OrmMemory).where(OrmMemory.id.in_(ids))
            rows = list((await s.execute(stmt)).scalars().all())
        return [_memory_from_orm(r) for r in rows]

    async def get_unembedded_memories(self, ids: list[str]) -> list[TapestryMemory]:
        if not ids:
            return []
        async with self._auto_session() as s:
            stmt = select(OrmMemory).where(
                OrmMemory.id.in_(ids),
                OrmMemory.embedding.is_(None),
            )
            rows = list((await s.execute(stmt)).scalars().all())
        return [_memory_from_orm(r) for r in rows]

    async def update_memory(self, memory: TapestryMemory) -> None:
        async with self._auto_session() as s:
            row = await s.get(OrmMemory, memory.id)
            if row is None:
                raise ValueError(f"Memory {memory.id} not found")
            row.content = memory.content
            row.from_date = memory.from_date
            row.to_date = memory.to_date
            row.embedding = memory.embedding
            row.status = memory.status
            row.superseded_by = memory.superseded_by
            row.source_memory_ids = memory.source_memory_ids

    async def list_memories(
        self,
        *,
        status: str | None = None,
        from_date: date | None = None,
        limit: int | None = None,
    ) -> list[TapestryMemory]:
        async with self._auto_session() as s:
            stmt = select(OrmMemory).order_by(OrmMemory.from_date)
            if status is not None:
                stmt = stmt.where(OrmMemory.status == status)
            if from_date is not None:
                stmt = stmt.where(OrmMemory.from_date >= from_date)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = list((await s.execute(stmt)).scalars().all())
        return [_memory_from_orm(r) for r in rows]

    async def count_memories(self, *, status: str | None = None) -> int:
        async with self._auto_session() as s:
            stmt = select(func.count()).select_from(OrmMemory)
            if status is not None:
                stmt = stmt.where(OrmMemory.status == status)
            return (await s.execute(stmt)).scalar() or 0

    async def search_memories(
        self,
        *,
        query_embedding: list[float] | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        top_k: int = 5,
    ) -> list[MemorySearchResult]:
        async with self._auto_session() as s:
            columns: list = [OrmMemory]
            distance_col = None

            if query_embedding is not None:
                distance_col = OrmMemory.embedding.cosine_distance(
                    query_embedding
                ).label("distance")
                columns.append(distance_col)

            stmt = select(*columns).where(OrmMemory.status == MemoryStatus.active.value)

            if query_embedding is not None:
                stmt = stmt.where(OrmMemory.embedding.isnot(None))
            if from_date is not None:
                stmt = stmt.where(OrmMemory.from_date >= from_date)
            if to_date is not None:
                stmt = stmt.where(OrmMemory.to_date <= to_date)

            if distance_col is not None:
                stmt = stmt.order_by(distance_col)
            else:
                stmt = stmt.order_by(OrmMemory.from_date.desc())

            stmt = stmt.limit(top_k)
            result = await s.execute(stmt)
            rows = result.all()

        results: list[MemorySearchResult] = []
        for row in rows:
            if query_embedding is not None:
                memory, distance = row
                similarity = 1.0 - distance
            else:
                (memory,) = row
                similarity = None
            results.append(
                MemorySearchResult(
                    id=memory.id,
                    content=memory.content,
                    from_date=memory.from_date,
                    to_date=memory.to_date,
                    similarity=similarity,
                )
            )
        return results

    async def get_refinable_memory_ids(self) -> list[str]:
        async with self._auto_session() as s:
            stmt = select(OrmMemory.id).where(
                OrmMemory.status == MemoryStatus.active.value,
                OrmMemory.embedding.isnot(None),
                OrmMemory.source_memory_ids.is_(None),
            )
            result = await s.execute(stmt)
        return [row[0] for row in result.all()]

    async def find_similar_memories(
        self,
        seed_id: str,
        *,
        date_proximity_days: int = 7,
        similarity_threshold: float = 0.4,
        max_candidates: int = 10,
    ) -> list[str]:
        async with self._auto_session() as s:
            seed = await s.get(OrmMemory, seed_id)
            if seed is None or seed.embedding is None:
                return []

            cosine_threshold = 1.0 - similarity_threshold
            proximity = func.make_interval(0, 0, 0, date_proximity_days)

            stmt = (
                select(OrmMemory.id)
                .where(
                    and_(
                        OrmMemory.status == MemoryStatus.active.value,
                        OrmMemory.embedding.isnot(None),
                        OrmMemory.id != seed_id,
                        OrmMemory.from_date <= literal(seed.to_date) + proximity,
                        OrmMemory.to_date >= literal(seed.from_date) - proximity,
                        OrmMemory.embedding.cosine_distance(seed.embedding)
                        < cosine_threshold,
                    )
                )
                .order_by(OrmMemory.embedding.cosine_distance(seed.embedding))
                .limit(max_candidates)
            )
            result = await s.execute(stmt)
        return [row[0] for row in result.all()]

    # ── Profiles ─────────────────────────────────────────────────────

    async def get_latest_profile(self) -> TapestryProfile | None:
        async with self._auto_session() as s:
            stmt = select(OrmProfile).order_by(OrmProfile.generated_at.desc()).limit(1)
            row = (await s.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return _profile_from_orm(row)

    async def save_profile(self, profile: TapestryProfile) -> None:
        async with self._auto_session() as s:
            existing = await s.get(OrmProfile, profile.id)
            if existing is not None:
                existing.content = profile.content
                existing.generated_at = profile.generated_at
                existing.memory_count = profile.memory_count
            else:
                s.add(
                    OrmProfile(
                        id=profile.id,
                        content=profile.content,
                        generated_at=profile.generated_at,
                        memory_count=profile.memory_count,
                    )
                )


# ── ORM → domain converters ─────────────────────────────────────────


def _archive_from_orm(row: OrmArchive) -> Archive:
    return Archive(
        provider=row.provider,
        id=row.id,
        status=row.status,
        file_uris=row.file_uris,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _task_from_orm(row: OrmEtlTask) -> EtlTask:
    return EtlTask(
        archive_id=row.archive_id,
        provider=row.provider,
        interaction_type=row.interaction_type,
        source_uri=row.source_uri,
        id=row.id,
        status=row.status,
        extracted_count=row.extracted_count,
        transformed_count=row.transformed_count,
        uploaded_count=row.uploaded_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _thread_from_orm(row: OrmThread) -> Thread:
    return Thread(
        unique_key=row.unique_key,
        provider=row.provider,
        interaction_type=row.interaction_type,
        preview=row.preview,
        payload=row.payload,
        version=row.version,
        asat=row.asat,
        id=row.id,
        etl_task_id=row.etl_task_id,
        asset_uri=row.asset_uri,
        source=row.source,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _memory_from_orm(row: OrmMemory) -> TapestryMemory:
    return TapestryMemory(
        content=row.content,
        from_date=row.from_date,
        to_date=row.to_date,
        group_id=row.group_id,
        id=row.id,
        embedding=list(row.embedding) if row.embedding is not None else None,
        status=row.status,
        superseded_by=row.superseded_by,
        source_memory_ids=row.source_memory_ids,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _batch_from_orm(row: OrmBatch) -> Batch:
    return Batch(
        batch_number=row.batch_number,
        category=row.category,
        states=row.states,
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _profile_from_orm(row: OrmProfile) -> TapestryProfile:
    return TapestryProfile(
        content=row.content,
        generated_at=row.generated_at,
        memory_count=row.memory_count,
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _flush_thread_batch(session: AsyncSession, batch: list[dict]) -> int:
    stmt = (
        insert(OrmThread)
        .values(batch)
        .on_conflict_do_nothing(index_elements=["unique_key"])
    )
    result = await session.execute(stmt)
    return result.rowcount  # type: ignore[return-value]

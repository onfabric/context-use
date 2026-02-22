from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from context_use.db.base import DatabaseBackend
from context_use.db.models import Base


class PostgresBackend(DatabaseBackend):
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

    def get_engine(self) -> AsyncEngine:
        return self._engine

    def get_session(self) -> AsyncSession:
        return self._session_factory()

    async def init_db(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)

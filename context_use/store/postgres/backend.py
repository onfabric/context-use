from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import TracebackType

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from context_use.store.postgres.orm import Base


class DatabaseBackend(ABC):
    """Abstract base class for database backends."""

    @abstractmethod
    def get_engine(self) -> AsyncEngine: ...

    @abstractmethod
    def get_session(self) -> AsyncSession: ...

    @abstractmethod
    async def init_db(self) -> None: ...

    @abstractmethod
    async def reset_db(self) -> None: ...

    async def close(self) -> None:
        """Dispose of the connection pool and release all resources."""
        await self.get_engine().dispose()

    async def __aenter__(self) -> DatabaseBackend:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    @asynccontextmanager
    async def session_scope(self) -> AsyncGenerator[AsyncSession]:
        """Provide a transactional scope around a series of operations."""
        session = self.get_session()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


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

    async def reset_db(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)

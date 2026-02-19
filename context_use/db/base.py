from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class DatabaseBackend(ABC):
    """Abstract base class for database backends."""

    @abstractmethod
    def get_engine(self) -> AsyncEngine: ...

    @abstractmethod
    def get_session(self) -> AsyncSession: ...

    @abstractmethod
    async def init_db(self) -> None: ...

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

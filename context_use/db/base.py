from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import Engine
from sqlalchemy.orm import Session


class DatabaseBackend(ABC):
    """Abstract base class for database backends."""

    @abstractmethod
    def get_engine(self) -> Engine:
        """Return the SQLAlchemy engine."""
        ...

    @abstractmethod
    def get_session(self) -> Session:
        """Return a new SQLAlchemy session."""
        ...

    @abstractmethod
    def init_db(self) -> None:
        """Create all tables from metadata."""
        ...

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Provide a transactional scope around a series of operations."""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


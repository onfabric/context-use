from __future__ import annotations

try:
    import psycopg2  # noqa: F401
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from contextuse.db.base import DatabaseBackend
from contextuse.models.base import Base


class PostgresBackend(DatabaseBackend):
    """PostgreSQL database backend.

    Requires ``psycopg2-binary``.  Install via::

        pip install "contextuse[postgres]"
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "contextuse",
        user: str = "postgres",
        password: str = "",
    ) -> None:
        if psycopg2 is None:
            raise ImportError(
                "psycopg2-binary is required for PostgresBackend. "
                "Install with: pip install 'contextuse[postgres]'"
            )
        url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        self._engine = create_engine(url, echo=False)
        self._session_factory = sessionmaker(bind=self._engine)

    def get_engine(self) -> Engine:
        return self._engine

    def get_session(self) -> Session:
        return self._session_factory()

    def init_db(self) -> None:
        Base.metadata.create_all(self._engine)


from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from context_use.db.base import DatabaseBackend
from context_use.models.base import Base


class SQLiteBackend(DatabaseBackend):

    def __init__(self, path: str = ":memory:") -> None:
        if path == ":memory:":
            url = "sqlite:///:memory:"
        else:
            url = f"sqlite:///{path}"
        self._engine = create_engine(url, echo=False)
        self._session_factory = sessionmaker(bind=self._engine)

    def get_engine(self) -> Engine:
        return self._engine

    def get_session(self) -> Session:
        return self._session_factory()

    def init_db(self) -> None:
        Base.metadata.create_all(self._engine)


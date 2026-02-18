from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session


class DatabaseBackend(ABC):
    @abstractmethod
    def get_engine(self) -> Engine: ...

    @abstractmethod
    def get_session(self) -> Session: ...

    @abstractmethod
    def init_db(self) -> None: ...

    @contextmanager
    def session_scope(self) -> Generator[Session]:
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

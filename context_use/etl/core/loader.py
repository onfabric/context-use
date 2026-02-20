from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from context_use.etl.core.types import ThreadRow
from context_use.etl.models.etl_task import EtlTask


class Loader(ABC):
    """Consumes :class:`ThreadRow` instances and persists them."""

    @abstractmethod
    async def load(self, rows: Iterable[ThreadRow], task: EtlTask) -> int:
        """Persist thread rows.

        Returns:
            Count of rows successfully loaded (inserted, not deduplicated).
        """
        ...


class DbLoader(Loader):
    """Inserts :class:`ThreadRow` instances directly into Postgres."""

    # TODO: Replace row-at-a-time inserts with psql_insert_copy
    #  (PostgreSQL COPY + temp table) for better bulk-insert performance.

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, rows: Iterable[ThreadRow], task: EtlTask) -> int:
        from sqlalchemy.dialects.postgresql import insert

        from context_use.etl.models.thread import Thread

        total = 0
        for row in rows:
            stmt = (
                insert(Thread)
                .values(
                    unique_key=row.unique_key,
                    etl_task_id=task.id,
                    provider=row.provider,
                    interaction_type=row.interaction_type,
                    preview=row.preview,
                    payload=row.payload,
                    source=row.source,
                    version=row.version,
                    asat=row.asat,
                    asset_uri=row.asset_uri,
                )
                .on_conflict_do_nothing(
                    index_elements=["unique_key"],
                )
            )
            result = await self._session.execute(stmt)
            total += result.rowcount  # type: ignore[attr-defined]
        return total

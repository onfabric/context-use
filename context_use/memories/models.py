from __future__ import annotations

from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from context_use.etl.models.base import Base, TimeStampMixin, _new_uuid

EMBEDDING_DIMENSIONS = 3072


class TapestryMemory(TimeStampMixin, Base):
    """A single memory covering a date range."""

    __tablename__ = "tapestry_memories"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )

    tapestry_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)

    group_key: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        comment="Group that produced this memory (e.g. window date range)",
    )

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_tapestry_memories_tapestry_id", "tapestry_id"),
        Index("idx_tapestry_memories_from_date", "from_date"),
        Index("idx_tapestry_memories_to_date", "to_date"),
        Index("idx_tapestry_memories_group_key", "group_key"),
    )

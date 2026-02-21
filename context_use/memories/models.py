from __future__ import annotations

import enum
from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from context_use.db.models import Base, TimeStampMixin, new_uuid

EMBEDDING_DIMENSIONS = 3072


class MemoryStatus(enum.StrEnum):
    active = "active"
    superseded = "superseded"


class TapestryMemory(TimeStampMixin, Base):
    """A single memory covering a date range."""

    __tablename__ = "tapestry_memories"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_uuid,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)

    group_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="UUID of the group instance that produced this memory",
    )

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=MemoryStatus.active.value,
        server_default=MemoryStatus.active.value,
    )

    superseded_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("tapestry_memories.id"),
        nullable=True,
    )

    source_memory_ids: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="IDs of memories consumed to produce this refined memory",
    )

    __table_args__ = (
        Index("idx_tapestry_memories_from_date", "from_date"),
        Index("idx_tapestry_memories_to_date", "to_date"),
        Index("idx_tapestry_memories_group_id", "group_id"),
        Index("idx_tapestry_memories_status", "status"),
    )

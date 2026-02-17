from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from contextuse.models.base import Base, TimeStampMixin, _new_uuid

if TYPE_CHECKING:
    from contextuse.models.etl_task import EtlTask


class ArchiveStatus(str, enum.Enum):
    CREATED = "created"
    COMPLETED = "completed"
    FAILED = "failed"


class Archive(TimeStampMixin, Base):
    __tablename__ = "archives"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    tapestry_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=ArchiveStatus.CREATED.value,
    )

    etl_tasks: Mapped[list[EtlTask]] = relationship(
        "EtlTask", back_populates="archive", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_archives_provider", "provider"),
        Index("idx_archives_tapestry_id", "tapestry_id"),
    )


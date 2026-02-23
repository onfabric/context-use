from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from context_use.db.models import Base, TimeStampMixin
from context_use.models.archive import ArchiveStatus
from context_use.models.utils import generate_id

if TYPE_CHECKING:
    from context_use.etl.models.etl_task import EtlTask

__all__ = ["Archive", "ArchiveStatus"]


class Archive(TimeStampMixin, Base):
    __tablename__ = "archives"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_id,
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=ArchiveStatus.CREATED.value,
    )
    file_uris: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    etl_tasks: Mapped[list[EtlTask]] = relationship(
        "EtlTask", back_populates="archive", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_archives_provider", "provider"),)

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from context_use.models.base import Base, TimeStampMixin, _new_uuid

if TYPE_CHECKING:
    from context_use.models.etl_task import EtlTask


class ArchiveStatus(StrEnum):
    CREATED = "created"
    COMPLETED = "completed"
    FAILED = "failed"


class Archive(TimeStampMixin, Base):
    __tablename__ = "archives"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=ArchiveStatus.CREATED
    )

    etl_tasks: Mapped[list[EtlTask]] = relationship(
        "EtlTask",
        back_populates="archive",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("ix_archives_provider", "provider"),)

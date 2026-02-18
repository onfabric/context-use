from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from context_use.models.base import Base, TimeStampMixin, _new_uuid

if TYPE_CHECKING:
    from context_use.models.archive import Archive


class EtlTaskStatus(StrEnum):
    CREATED = "created"
    EXTRACTING = "extracting"
    TRANSFORMING = "transforming"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


class EtlTask(TimeStampMixin, Base):
    __tablename__ = "etl_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    archive_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("archives.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    interaction_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=EtlTaskStatus.CREATED
    )
    extracted_count: Mapped[int] = mapped_column(Integer, default=0)
    transformed_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_count: Mapped[int] = mapped_column(Integer, default=0)

    archive: Mapped[Archive] = relationship(
        "Archive",
        uselist=False,
        back_populates="etl_tasks",
    )

    __table_args__ = (Index("ix_etl_tasks_archive_id", "archive_id"),)

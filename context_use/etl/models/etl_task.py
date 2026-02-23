from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from context_use.db.models import Base, TimeStampMixin
from context_use.etl.models.archive import Archive
from context_use.models.etl_task import EtlTaskStatus
from context_use.models.utils import generate_uuidv4

__all__ = ["EtlTask", "EtlTaskStatus"]


class EtlTask(TimeStampMixin, Base):
    __tablename__ = "etl_tasks"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuidv4,
    )
    archive_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("archives.id"),
        nullable=False,
    )
    archive: Mapped[Archive] = relationship(uselist=False, back_populates="etl_tasks")

    provider: Mapped[str] = mapped_column(String, nullable=False)
    interaction_type: Mapped[str] = mapped_column(String, nullable=False)
    source_uri: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=EtlTaskStatus.CREATED.value,
    )

    extracted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transformed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("idx_etl_tasks_archive_id", "archive_id"),)

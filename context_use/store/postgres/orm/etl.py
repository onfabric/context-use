# pyright: reportMissingImports=false
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from context_use.models.archive import ArchiveStatus
from context_use.models.etl_task import EtlTaskStatus
from context_use.models.utils import generate_uuidv4
from context_use.store.postgres.orm.base import Base, TimeStampMixin


class Archive(TimeStampMixin, Base):
    __tablename__ = "archives"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuidv4,
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
    source_uris: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=EtlTaskStatus.CREATED.value,
    )

    extracted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transformed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("idx_etl_tasks_archive_id", "archive_id"),)


class Thread(TimeStampMixin, Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuidv4,
    )
    unique_key: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
    )
    etl_task_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("etl_tasks.id"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    interaction_type: Mapped[str] = mapped_column(String, nullable=False)
    preview: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    asset_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String, nullable=False)
    asat: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_threads_unique_key", "unique_key", unique=True),
        Index("idx_threads_etl_task_id", "etl_task_id"),
        Index("idx_threads_provider", "provider"),
        Index("idx_threads_interaction_type", "interaction_type"),
        Index("idx_threads_asat", "asat"),
    )

    @property
    def is_asset(self) -> bool:
        return self.asset_uri is not None

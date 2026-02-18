from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from context_use.etl.models.base import Base, TimeStampMixin, _new_uuid


class Thread(TimeStampMixin, Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )

    unique_key: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
    )

    tapestry_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
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
        Index("idx_threads_tapestry_id", "tapestry_id"),
        Index("idx_threads_etl_task_id", "etl_task_id"),
        Index("idx_threads_provider", "provider"),
        Index("idx_threads_interaction_type", "interaction_type"),
        Index("idx_threads_asat", "asat"),
    )

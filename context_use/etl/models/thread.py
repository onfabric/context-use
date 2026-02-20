from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from context_use.db.models import Base, TimeStampMixin, new_uuid
from context_use.etl.payload.core import make_thread_payload


class Thread(TimeStampMixin, Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_uuid,
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

    __allow_unmapped__ = True
    _parsed_payload: object | None = None  # per-instance lazy cache

    def _get_parsed_payload(self):
        if self._parsed_payload is None:
            self._parsed_payload = make_thread_payload(self.payload)
        return self._parsed_payload

    @property
    def is_asset(self) -> bool:
        return self.asset_uri is not None

    @property
    def is_inbound(self) -> bool:
        """Whether this thread was performed by someone else toward the user."""
        return self._get_parsed_payload().is_inbound()

    def get_message_content(self) -> str | None:
        """Get the text content of a message thread (None for non-message threads)."""
        return self._get_parsed_payload().get_message_content()

    def get_collection(self) -> str | None:
        """Get collection ID for this thread."""
        return self._get_parsed_payload().get_collection()

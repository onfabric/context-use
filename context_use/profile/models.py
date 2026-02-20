from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from context_use.etl.models.base import Base, TimeStampMixin, _new_uuid


class TapestryProfile(TimeStampMixin, Base):
    """A user profile distilled from memories.

    One row per tapestry, replaced on each regeneration.  ``content``
    holds free-form markdown produced by the LLM.
    """

    __tablename__ = "tapestry_profiles"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )

    tapestry_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    memory_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of active memories used to generate this profile",
    )

    __table_args__ = (Index("idx_tapestry_profiles_tapestry_id", "tapestry_id"),)

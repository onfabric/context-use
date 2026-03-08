from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from context_use.store.postgres.orm.base import Base, TimeStampMixin


class UserProfile(TimeStampMixin, Base):
    """Exactly-one-row table holding the user profile document."""

    __tablename__ = "user_profiles"

    singleton: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        default=1,
        insert_default=1,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("singleton = 1", name="ck_user_profiles_singleton"),
    )

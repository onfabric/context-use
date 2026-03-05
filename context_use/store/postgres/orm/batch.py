from __future__ import annotations

from abc import abstractmethod

from sqlalchemy import JSON, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.attributes import flag_modified

from context_use.batch.registry import parse_batch_state
from context_use.batch.states import CreatedState, State
from context_use.models.batch import BatchCategory
from context_use.models.utils import generate_uuidv4
from context_use.store.postgres.orm.base import Base, TimeStampMixin


def _default_created_state() -> list:
    return [CreatedState().model_dump(mode="json")]


class BatchStateMixin:
    """Mixin providing ``states`` JSON column and state-machine helpers.

    ``states`` is a JSON array where index 0 is the *current* state.
    New states are prepended; same-status updates replace index 0 in-place.
    """

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuidv4,
        comment="Unique identifier for the batch",
    )
    states: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=_default_created_state,
        comment="State array — current state at index 0",
    )

    @abstractmethod
    def _parse_state(self, state_dict: dict) -> State:
        """Subclasses convert a raw dict into the correct State subclass."""

    @property
    def current_state(self) -> State:
        if not self.states:
            raise ValueError(f"Batch {self.id} has no states")
        return self._parse_state(self.states[0])

    def update_state(self, new_state: State) -> None:
        """Prepend *new_state*; replace head if the status is unchanged (polling)."""
        new_dict = new_state.model_dump(mode="json")

        if self.states:
            if self.states[0].get("status") == new_dict.get("status"):
                self.states[0] = new_dict
            else:
                self.states.insert(0, new_dict)
        else:
            self.states.insert(0, new_dict)

        flag_modified(self, "states")

    @property
    def state_history(self) -> list[State]:
        return [self._parse_state(s) for s in reversed(self.states)]

    @property
    def current_status(self) -> str:
        return self.current_state.status


class Batch(BatchStateMixin, TimeStampMixin, Base):
    """A batch of threads to be processed by a pipeline."""

    __tablename__ = "batches"

    def _parse_state(self, state_dict: dict) -> State:
        if self.category is None:
            raise ValueError(f"Batch {self.id} has no category")
        return parse_batch_state(state_dict, BatchCategory(self.category))

    batch_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Batch order (1, 2, …)",
    )
    category: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    __table_args__ = (Index("idx_batches_category", "category"),)


class BatchThread(Base):
    """Explicit mapping of threads to batches, identified by group_id."""

    __tablename__ = "batch_threads"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuidv4,
    )
    batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("batches.id"),
        nullable=False,
    )
    thread_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("threads.id"),
        nullable=False,
    )
    group_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="UUID identifying this group instance (used as OpenAI custom_id)",
    )

    __table_args__ = (
        Index("idx_batch_threads_batch_id", "batch_id"),
        Index("idx_batch_threads_thread_id", "thread_id"),
        Index("idx_batch_threads_group_id", "group_id"),
    )

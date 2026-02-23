from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from context_use.models.utils import generate_uuidv4

if TYPE_CHECKING:
    from context_use.batch.states import State


def _utcnow() -> datetime:
    return datetime.now(UTC)


class BatchCategory(enum.StrEnum):
    """Extensible registry of pipeline categories."""

    memories = "memories"
    refinement = "refinement"


@dataclass
class Batch:
    """A batch of thread groups to be processed by a pipeline."""

    batch_number: int
    category: str
    states: list[dict]

    id: str = field(default_factory=generate_uuidv4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def parse_current_state(self) -> State:
        """Parse the head of ``states`` into a typed State object."""
        from context_use.batch.models import parse_batch_state

        if not self.states:
            raise ValueError(f"Batch {self.id} has no states")
        return parse_batch_state(self.states[0], BatchCategory(self.category))

    @property
    def current_status(self) -> str:
        if not self.states:
            raise ValueError(f"Batch {self.id} has no states")
        return self.states[0].get("status", "")

    def push_state(self, new_state: State) -> None:
        """Prepend *new_state*; replace head if the status is unchanged (polling)."""
        new_dict = new_state.model_dump(mode="json")
        if self.states:
            if self.states[0].get("status") == new_dict.get("status"):
                self.states[0] = new_dict
            else:
                self.states.insert(0, new_dict)
        else:
            self.states.insert(0, new_dict)


@dataclass
class BatchThread:
    """Mapping of a thread to a batch, identified by group_id."""

    batch_id: str
    thread_id: str
    group_id: str

    id: str = field(default_factory=generate_uuidv4)

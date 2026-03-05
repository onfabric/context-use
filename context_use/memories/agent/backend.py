from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from context_use.llm.base import BaseLLMClient
    from context_use.store.base import Store


@dataclass
class AgentResult:
    """Returned by every :class:`AgentBackend` implementation."""

    summary: str
    """Human-readable summary of every action taken, or a note that nothing was done."""


class AgentBackend(ABC):
    """Interface for personal agent backends."""

    @abstractmethod
    async def run(
        self,
        store: Store,
        llm_client: BaseLLMClient,
        message: str,
    ) -> AgentResult:
        """Execute the agent with *message* as the user task and return a summary."""
        ...

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from context_use.llm.base import BaseLLMClient
    from context_use.store.base import Store


@dataclass
class RefinementResult:
    """Returned by every :class:`RefinementBackend` implementation."""

    summary: str
    """Human-readable summary of every change made, or a note that no
    changes were necessary."""


class RefinementBackend(ABC):
    """Interface for memory refinement backends."""

    @abstractmethod
    async def run(self, store: Store, llm_client: BaseLLMClient) -> RefinementResult:
        """Execute refinement and return a summary of changes made."""
        ...

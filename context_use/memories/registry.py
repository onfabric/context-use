from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from context_use.batch.grouper import ThreadGrouper
from context_use.memories.prompt.base import BasePromptBuilder, GroupContext


@dataclass(frozen=True)
class MemoryConfig:
    """Everything the memory pipeline needs for one interaction type."""

    prompt_builder: type[BasePromptBuilder]
    grouper: type[ThreadGrouper]
    prompt_builder_kwargs: dict[str, Any] = field(default_factory=dict)
    grouper_kwargs: dict[str, Any] = field(default_factory=dict)

    def create_prompt_builder(self, contexts: list[GroupContext]) -> BasePromptBuilder:
        return self.prompt_builder(contexts, **self.prompt_builder_kwargs)

    def create_grouper(self) -> ThreadGrouper:
        return self.grouper(**self.grouper_kwargs)


_MEMORY_REGISTRY: dict[str, MemoryConfig] = {}


def register_memory_config(interaction_type: str, config: MemoryConfig) -> None:
    """Register a memory pipeline configuration for an interaction type."""
    _MEMORY_REGISTRY[interaction_type] = config


def get_memory_config(interaction_type: str) -> MemoryConfig:
    """Look up the memory config for *interaction_type*.

    Raises ``KeyError`` if no config has been registered.
    """
    try:
        return _MEMORY_REGISTRY[interaction_type]
    except KeyError:
        raise KeyError(
            f"No memory config registered for interaction type: {interaction_type}"
        ) from None

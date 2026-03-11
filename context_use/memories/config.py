from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from context_use.batch.grouper import ThreadGrouper
from context_use.memories.prompt.base import BasePromptBuilder, GroupContext


@dataclass(frozen=True)
class MemoryConfig:
    """Everything the memory pipeline needs for one interaction type.

    Providers compose this from reusable building blocks (prompt builders,
    groupers) and reference it in their :class:`InteractionConfig`.
    """

    prompt_builder: type[BasePromptBuilder]
    grouper: type[ThreadGrouper]
    prompt_builder_kwargs: dict[str, Any] = field(default_factory=dict)
    grouper_kwargs: dict[str, Any] = field(default_factory=dict)

    def create_prompt_builder(self, contexts: list[GroupContext]) -> BasePromptBuilder:
        return self.prompt_builder(contexts, **self.prompt_builder_kwargs)

    def create_grouper(self) -> ThreadGrouper:
        return self.grouper(**self.grouper_kwargs)

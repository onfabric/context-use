from __future__ import annotations

import pytest

from context_use.memories.prompt.base import GroupContext
from context_use.memories.prompt.conversation import (
    AgentConversationMemoryPromptBuilder,
)


@pytest.fixture(scope="session")
def prompt_builders(
    group_contexts: list[GroupContext],
) -> list[AgentConversationMemoryPromptBuilder]:
    return [AgentConversationMemoryPromptBuilder(ctx) for ctx in group_contexts]

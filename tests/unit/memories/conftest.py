from __future__ import annotations

import pytest

from context_use.memories.prompt.base import GroupContext
from context_use.memories.prompt.conversation import (
    AgentConversationMemoryPromptBuilder,
)


@pytest.fixture(scope="session")
def prompt_builder(
    group_contexts: list[GroupContext],
) -> AgentConversationMemoryPromptBuilder:
    return AgentConversationMemoryPromptBuilder(group_contexts)

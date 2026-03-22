from __future__ import annotations

import pytest

from context_use.llm.litellm.clients import LiteLLMSyncClient
from context_use.memories.prompt.base import MemorySchema
from context_use.memories.prompt.conversation import (
    AgentConversationMemoryPromptBuilder,
)

from .scenarios import EvalScenario

pytestmark = [pytest.mark.eval]


async def test_context_impact(
    scenario: EvalScenario,
    llm_client: LiteLLMSyncClient,
) -> None:
    prompts = [
        AgentConversationMemoryPromptBuilder(ctx).build() for ctx in scenario.contexts
    ]

    print(f"\n{'=' * 70}")
    print(f"SCENARIO : {scenario.id}")
    print(f"          {scenario.description}")
    print(f"{'=' * 70}")

    for prompt in prompts:
        result: MemorySchema = await llm_client.structured_completion(
            prompt, MemorySchema
        )

        assert result.memories, (
            f"[{scenario.id}] No memories for group {prompt.item_id}"
        )

        print(f"\n  Group {prompt.item_id[:8]}…")
        for memory in result.memories:
            print(f"    [{memory.from_date}] {memory.content}")

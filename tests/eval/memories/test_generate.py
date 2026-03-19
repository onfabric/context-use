from __future__ import annotations

import re

import pytest

from context_use.llm.base import PromptItem
from context_use.llm.litellm.clients import LiteLLMSyncClient
from context_use.memories.prompt.base import MemorySchema

pytestmark = [pytest.mark.eval]


async def test_generates_memories_for_each_conversation(
    llm_client: LiteLLMSyncClient,
    prompts: list[PromptItem],
    conversation_groups,
) -> None:
    assert len(prompts) == len(conversation_groups)

    for prompt in prompts:
        result: MemorySchema = await llm_client.structured_completion(
            prompt, MemorySchema
        )

        assert result.memories, f"No memories generated for group {prompt.item_id}"

        for memory in result.memories:
            assert memory.content.strip(), "Memory content is empty"
            assert re.match(r"\d{4}-\d{2}-\d{2}", memory.from_date), (
                f"Invalid from_date: {memory.from_date!r}"
            )
            assert re.match(r"\d{4}-\d{2}-\d{2}", memory.to_date), (
                f"Invalid to_date: {memory.to_date!r}"
            )
            assert memory.from_date <= memory.to_date, (
                f"from_date {memory.from_date} is after to_date {memory.to_date}"
            )

        print(f"\n--- Group {prompt.item_id} ---")
        for memory in result.memories:
            print(f"  [{memory.from_date}] {memory.content}")


@pytest.mark.parametrize(
    "match_keywords,expected_keywords",
    [
        (
            ["wispr", "prosumer"],
            ["startup", "open-source", "developer", "posthog", "wispr"],
        ),
        (["pyright", "pydantic"], ["python", "type", "pyright", "pydantic"]),
        (["ramen", "cacio"], ["italian", "japanese", "ramen", "cacio"]),
    ],
)
async def test_memories_are_relevant_to_conversation(
    llm_client: LiteLLMSyncClient,
    prompts: list[PromptItem],
    match_keywords: list[str],
    expected_keywords: list[str],
) -> None:
    matching = [
        p for p in prompts if any(kw in p.prompt.lower() for kw in match_keywords)
    ]
    assert matching, f"No prompt found containing any of {match_keywords}"

    result: MemorySchema = await llm_client.structured_completion(
        matching[0], MemorySchema
    )
    combined = " ".join(m.content.lower() for m in result.memories)

    matches = [kw for kw in expected_keywords if kw in combined]
    assert matches, (
        f"Expected at least one of {expected_keywords} in memories "
        f"(matched prompt via {match_keywords}), "
        f"got: {combined[:200]}"
    )

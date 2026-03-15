from __future__ import annotations

from context_use.batch.grouper import ThreadGroup
from context_use.memories.prompt.base import GroupContext
from context_use.memories.prompt.conversation import (
    AgentConversationMemoryPromptBuilder,
)


def test_has_content(prompt_builder: AgentConversationMemoryPromptBuilder) -> None:
    assert prompt_builder.has_content()


def test_builds_one_prompt_per_conversation(
    prompt_builder: AgentConversationMemoryPromptBuilder,
    conversation_groups: list[ThreadGroup],
) -> None:
    prompts = prompt_builder.build()
    assert len(prompts) == len(conversation_groups)


def test_prompt_ids_match_group_ids(
    prompt_builder: AgentConversationMemoryPromptBuilder,
    group_contexts: list[GroupContext],
) -> None:
    prompts = prompt_builder.build()
    prompt_ids = {p.item_id for p in prompts}
    context_ids = {ctx.group_id for ctx in group_contexts}
    assert prompt_ids == context_ids


def test_transcript_contains_user_and_assistant_turns(
    prompt_builder: AgentConversationMemoryPromptBuilder,
) -> None:
    prompts = prompt_builder.build()
    for prompt in prompts:
        assert "[ME " in prompt.prompt, "Expected [ME ...] label in transcript"
        assert "[ASSISTANT " in prompt.prompt, (
            "Expected [ASSISTANT ...] label in transcript"
        )


def test_transcript_contains_fixture_content(
    prompt_builder: AgentConversationMemoryPromptBuilder,
) -> None:
    prompts = prompt_builder.build()
    combined = "\n".join(p.prompt for p in prompts)
    assert "wispr flow" in combined.lower()
    assert "cacio e pepe" in combined.lower()
    assert "pyright" in combined.lower()


def test_response_schema_is_set(
    prompt_builder: AgentConversationMemoryPromptBuilder,
) -> None:
    prompts = prompt_builder.build()
    for prompt in prompts:
        assert prompt.response_schema
        assert "memories" in prompt.response_schema.get("properties", {})


def test_empty_group_produces_no_prompt() -> None:
    ctx = GroupContext(group_id="empty", new_threads=[])
    builder = AgentConversationMemoryPromptBuilder([ctx])
    assert not builder.has_content()
    assert builder.build() == []


def test_inbound_messages_truncated_at_2000_chars(
    conversation_groups: list[ThreadGroup],
) -> None:
    prompts = AgentConversationMemoryPromptBuilder(
        [
            GroupContext(group_id=g.group_id, new_threads=g.threads)
            for g in conversation_groups
        ]
    ).build()
    for prompt in prompts:
        for line in prompt.prompt.splitlines():
            if line.startswith("[ASSISTANT "):
                content = line.split("] ", 1)[1] if "] " in line else ""
                assert len(content) <= 2000 + len(" [...]"), (
                    "Assistant message not truncated"
                )

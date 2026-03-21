from __future__ import annotations

from context_use.batch.grouper import ThreadGroup
from context_use.memories.prompt.base import GroupContext
from context_use.memories.prompt.conversation import (
    AgentConversationMemoryPromptBuilder,
)


def test_has_content(
    prompt_builders: list[AgentConversationMemoryPromptBuilder],
) -> None:
    assert all(b.has_content() for b in prompt_builders)


def test_builds_one_prompt_per_conversation(
    prompt_builders: list[AgentConversationMemoryPromptBuilder],
    conversation_groups: list[ThreadGroup],
) -> None:
    prompts = [b.build() for b in prompt_builders]
    assert all(p is not None for p in prompts)
    assert len(prompts) == len(conversation_groups)


def test_prompt_ids_match_group_ids(
    prompt_builders: list[AgentConversationMemoryPromptBuilder],
    group_contexts: list[GroupContext],
) -> None:
    prompt_ids = {b.build().item_id for b in prompt_builders if b.build() is not None}  # type: ignore[union-attr]
    context_ids = {ctx.group_id for ctx in group_contexts}
    assert prompt_ids == context_ids


def test_transcript_contains_user_and_assistant_turns(
    prompt_builders: list[AgentConversationMemoryPromptBuilder],
) -> None:
    for builder in prompt_builders:
        item = builder.build()
        assert item is not None
        assert "[ME " in item.prompt, "Expected [ME ...] label in transcript"
        assert "[ASSISTANT " in item.prompt, (
            "Expected [ASSISTANT ...] label in transcript"
        )


def test_transcript_contains_fixture_content(
    prompt_builders: list[AgentConversationMemoryPromptBuilder],
) -> None:
    combined = "\n".join(
        b.build().prompt
        for b in prompt_builders
        if b.build() is not None  # type: ignore[union-attr]
    )
    assert "wispr flow" in combined.lower()
    assert "cacio e pepe" in combined.lower()
    assert "pyright" in combined.lower()


def test_response_schema_is_set(
    prompt_builders: list[AgentConversationMemoryPromptBuilder],
) -> None:
    for builder in prompt_builders:
        item = builder.build()
        assert item is not None
        assert item.response_schema
        assert "memories" in item.response_schema.get("properties", {})


def test_empty_group_produces_no_prompt() -> None:
    ctx = GroupContext(group_id="empty", new_threads=[])
    builder = AgentConversationMemoryPromptBuilder(ctx)
    assert not builder.has_content()
    assert builder.build() is None


def test_inbound_messages_truncated_at_2000_chars(
    conversation_groups: list[ThreadGroup],
) -> None:
    for g in conversation_groups:
        ctx = GroupContext(group_id=g.group_id, new_threads=g.threads)
        item = AgentConversationMemoryPromptBuilder(ctx).build()
        assert item is not None
        for line in item.prompt.splitlines():
            if line.startswith("[ASSISTANT "):
                content = line.split("] ", 1)[1] if "] " in line else ""
                assert len(content) <= 2000 + len(" [...]"), (
                    "Assistant message not truncated"
                )

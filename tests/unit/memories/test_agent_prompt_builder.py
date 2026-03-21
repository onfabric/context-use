from __future__ import annotations

from context_use.batch.grouper import ThreadGroup
from context_use.memories.prompt.agent import AgentToolConversationPromptBuilder
from context_use.memories.prompt.base import GroupContext


def test_no_response_schema(conversation_groups: list[ThreadGroup]) -> None:
    group = conversation_groups[0]
    ctx = GroupContext(group_id=group.group_id, new_threads=group.threads)
    item = AgentToolConversationPromptBuilder(ctx).build()
    assert item is not None
    assert item.response_schema is None


def test_prompt_contains_tool_instructions(
    conversation_groups: list[ThreadGroup],
) -> None:
    group = conversation_groups[0]
    ctx = GroupContext(group_id=group.group_id, new_threads=group.threads)
    item = AgentToolConversationPromptBuilder(ctx).build()
    assert item is not None
    assert "search_memories" in item.prompt
    assert "create_memory" in item.prompt
    assert "update_memory" in item.prompt


def test_prompt_contains_transcript(
    conversation_groups: list[ThreadGroup],
) -> None:
    group = conversation_groups[0]
    ctx = GroupContext(group_id=group.group_id, new_threads=group.threads)
    item = AgentToolConversationPromptBuilder(ctx).build()
    assert item is not None
    assert "## Transcript" in item.prompt
    assert "[ME " in item.prompt


def test_inbound_messages_truncated(
    conversation_groups: list[ThreadGroup],
) -> None:
    group = conversation_groups[0]
    ctx = GroupContext(group_id=group.group_id, new_threads=group.threads)
    item = AgentToolConversationPromptBuilder(ctx).build()
    assert item is not None
    for line in item.prompt.splitlines():
        if line.startswith("[ASSISTANT "):
            content = line.split("] ", 1)[1] if "] " in line else ""
            assert len(content) <= 2000 + len(" [...]")


def test_item_id_matches_group_id(
    conversation_groups: list[ThreadGroup],
) -> None:
    group = conversation_groups[0]
    ctx = GroupContext(group_id=group.group_id, new_threads=group.threads)
    item = AgentToolConversationPromptBuilder(ctx).build()
    assert item is not None
    assert item.item_id == group.group_id

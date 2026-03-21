from __future__ import annotations

import pytest

from context_use.batch.grouper import ThreadGroup
from context_use.memories.context import GroupContextBuilder


@pytest.fixture()
def builder() -> GroupContextBuilder:
    return GroupContextBuilder()


async def test_build_maps_group_to_context(
    builder: GroupContextBuilder,
    conversation_groups: list[ThreadGroup],
) -> None:
    group = conversation_groups[0]
    ctx = await builder.build(group)
    assert ctx.group_id == group.group_id
    assert ctx.new_threads == group.threads
    assert ctx.prior_memories == []
    assert ctx.recent_threads == []
    assert ctx.user_profile is None


async def test_build_many(
    builder: GroupContextBuilder,
    conversation_groups: list[ThreadGroup],
) -> None:
    contexts = await builder.build_many(conversation_groups)
    assert len(contexts) == len(conversation_groups)
    for ctx, group in zip(contexts, conversation_groups, strict=True):
        assert ctx.group_id == group.group_id
        assert ctx.new_threads == group.threads


async def test_build_empty_list(builder: GroupContextBuilder) -> None:
    assert await builder.build_many([]) == []

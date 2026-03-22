from __future__ import annotations

import pytest

from context_use.batch.grouper import ThreadGroup
from context_use.memories.context import GroupContextBuilder
from context_use.store.sqlite import SqliteStore


@pytest.fixture(scope="session")
async def builder(thread_store: SqliteStore) -> GroupContextBuilder:
    return GroupContextBuilder(thread_store)


async def test_build_maps_group_to_context(
    builder: GroupContextBuilder,
    conversation_groups: list[ThreadGroup],
) -> None:
    group = conversation_groups[0]
    ctx = await builder.build(group)
    assert ctx.group_id == group.group_id
    assert ctx.new_threads == tuple(sorted(group.threads, key=lambda t: t.asat))
    assert ctx.relevant_memories == []
    assert ctx.relevant_threads == []
    assert ctx.user_profile is None


async def test_build_many(
    builder: GroupContextBuilder,
    conversation_groups: list[ThreadGroup],
) -> None:
    contexts = await builder.build_many(conversation_groups)
    assert len(contexts) == len(conversation_groups)
    for ctx, group in zip(contexts, conversation_groups, strict=True):
        assert ctx.group_id == group.group_id
        assert ctx.new_threads == tuple(sorted(group.threads, key=lambda t: t.asat))


async def test_build_empty_list(thread_store: SqliteStore) -> None:
    builder = GroupContextBuilder(thread_store)
    assert await builder.build_many([]) == []

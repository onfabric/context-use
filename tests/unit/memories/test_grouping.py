from __future__ import annotations

from context_use.batch.grouper import ThreadGroup
from context_use.store.sqlite import SqliteStore


async def test_groups_one_per_conversation(
    conversation_groups: list[ThreadGroup],
) -> None:
    assert len(conversation_groups) == 3


async def test_each_group_has_multiple_threads(
    conversation_groups: list[ThreadGroup],
) -> None:
    for group in conversation_groups:
        assert len(group.threads) >= 2, (
            f"Group {group.group_id} has only {len(group.threads)} thread(s)"
        )


async def test_threads_within_group_are_chronological(
    conversation_groups: list[ThreadGroup],
) -> None:
    for group in conversation_groups:
        dates = [t.asat for t in group.threads]
        assert dates == sorted(dates), f"Group {group.group_id} threads are not sorted"


async def test_no_threads_lost(
    thread_store: SqliteStore, conversation_groups: list[ThreadGroup]
) -> None:
    all_threads = await thread_store.get_unprocessed_threads(
        interaction_types=["claude_conversations"]
    )
    grouped_ids = {t.id for g in conversation_groups for t in g.threads}
    assert grouped_ids == {t.id for t in all_threads}


async def test_each_group_belongs_to_single_conversation(
    conversation_groups: list[ThreadGroup],
) -> None:
    for group in conversation_groups:
        collections = {t.get_collection() for t in group.threads}
        assert len(collections) == 1, (
            f"Group {group.group_id} spans multiple conversations: {collections}"
        )


async def test_conversations_are_in_separate_groups(
    conversation_groups: list[ThreadGroup],
) -> None:
    collection_ids = [
        next(iter({t.get_collection() for t in g.threads})) for g in conversation_groups
    ]
    assert len(collection_ids) == len(set(collection_ids)), (
        "Two groups share the same conversation URL"
    )

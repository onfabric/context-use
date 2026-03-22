from __future__ import annotations

from typing import cast

from context_use.batch.grouper import ThreadGroup
from context_use.memories.prompt.base import GroupContext
from context_use.models.thread import NonEmptyThreads, Thread
from context_use.store.base import SortOrder, Store

_GROUP_RECENT_THREAD_LIMIT = 10


class GroupContextBuilder:
    """Builds ``GroupContext`` from ``ThreadGroup``, enriching with relevant context."""

    def __init__(self, store: Store) -> None:
        self._store = store

    async def build(self, group: ThreadGroup) -> GroupContext:
        new_threads = cast(
            NonEmptyThreads,
            tuple(sorted(group.threads, key=lambda t: t.asat)),
        )
        relevant_threads: list[Thread] = []
        cid = new_threads[0].collection_id
        if cid:
            new_keys = {t.unique_key for t in new_threads}
            fetch_limit = _GROUP_RECENT_THREAD_LIMIT + len(new_threads)
            recent_desc = await self._store.list_threads(
                collection_id=cid,
                interaction_type=new_threads[0].interaction_type,
                limit=fetch_limit,
                asat_order=SortOrder.DESC,
            )
            filtered = [t for t in recent_desc if t.unique_key not in new_keys]
            relevant_threads = list(reversed(filtered[:_GROUP_RECENT_THREAD_LIMIT]))
        return GroupContext(
            group_id=group.group_id,
            new_threads=new_threads,
            relevant_threads=relevant_threads,
        )

    async def build_many(self, groups: list[ThreadGroup]) -> list[GroupContext]:
        return [await self.build(g) for g in groups]

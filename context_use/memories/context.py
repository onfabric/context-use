from __future__ import annotations

from context_use.batch.grouper import ThreadGroup
from context_use.memories.prompt.base import GroupContext


class GroupContextBuilder:
    """Builds ``GroupContext`` from ``ThreadGroup``, enriching with prior context."""

    async def build(self, group: ThreadGroup) -> GroupContext:
        return GroupContext(
            group_id=group.group_id,
            new_threads=group.threads,
        )

    async def build_many(self, groups: list[ThreadGroup]) -> list[GroupContext]:
        return [await self.build(g) for g in groups]

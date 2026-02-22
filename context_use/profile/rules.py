from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from context_use.models.profile import TapestryProfile

if TYPE_CHECKING:
    from context_use.store.base import Store


class RegenerationRule(Protocol):
    """Extensible gate for skipping profile regeneration.

    Implementations return a reason string to skip, or ``None`` to allow.
    """

    async def should_skip(
        self,
        profile: TapestryProfile | None,
        store: Store,
    ) -> str | None: ...

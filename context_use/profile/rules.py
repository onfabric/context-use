from __future__ import annotations

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from context_use.profile.models import TapestryProfile


class RegenerationRule(Protocol):
    """Extensible gate for skipping profile regeneration.

    Implementations return a reason string to skip, or ``None`` to allow.
    """

    async def should_skip(
        self,
        profile: TapestryProfile | None,
        db: AsyncSession,
    ) -> str | None: ...

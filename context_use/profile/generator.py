from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_use.llm.base import LLMClient
from context_use.memories.models import MemoryStatus, TapestryMemory
from context_use.profile.models import TapestryProfile
from context_use.profile.prompt import build_profile_prompt

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_MONTHS = 6


async def generate_profile(
    db: AsyncSession,
    llm_client: LLMClient,
    *,
    current_profile: TapestryProfile | None = None,
    lookback_months: int = DEFAULT_LOOKBACK_MONTHS,
) -> TapestryProfile:
    """Generate or regenerate a user profile from active memories.

    Loads recent active memories, builds a prompt (including the existing
    profile if present), calls the LLM, and upserts the profile row.
    """
    memories = await _load_recent_memories(db, lookback_months)

    logger.info(
        "Generating profile from %d memories (lookback=%d months)",
        len(memories),
        lookback_months,
    )

    prompt = build_profile_prompt(
        memories=memories,
        current_profile=current_profile.content if current_profile else None,
    )

    content = await llm_client.completion(prompt)

    now = datetime.now(UTC)

    if current_profile is not None:
        current_profile.content = content
        current_profile.generated_at = now
        current_profile.memory_count = len(memories)
        profile = current_profile
    else:
        profile = TapestryProfile(
            content=content,
            generated_at=now,
            memory_count=len(memories),
        )
        db.add(profile)

    await db.flush()

    logger.info(
        "Profile generated (%d chars, %d memories)",
        len(content),
        len(memories),
    )
    return profile


async def _load_recent_memories(
    db: AsyncSession,
    lookback_months: int,
) -> list[TapestryMemory]:
    cutoff = datetime.now(UTC).date() - timedelta(days=lookback_months * 30)

    stmt = select(TapestryMemory).where(
        TapestryMemory.status == MemoryStatus.active.value,
        TapestryMemory.from_date >= cutoff,
    )

    result = await db.execute(stmt.order_by(TapestryMemory.from_date))
    return list(result.scalars().all())

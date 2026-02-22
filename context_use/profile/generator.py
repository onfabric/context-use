from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from context_use.llm.base import LLMClient
from context_use.models.memory import MemoryStatus
from context_use.models.profile import TapestryProfile
from context_use.profile.prompt import build_profile_prompt

if TYPE_CHECKING:
    from context_use.store.base import Store

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_MONTHS = 6


async def generate_profile(
    store: Store,
    llm_client: LLMClient,
    *,
    current_profile: TapestryProfile | None = None,
    lookback_months: int = DEFAULT_LOOKBACK_MONTHS,
) -> TapestryProfile:
    """Generate or regenerate a user profile from active memories.

    Loads recent active memories, builds a prompt (including the existing
    profile if present), calls the LLM, and upserts the profile row.
    """
    cutoff = datetime.now(UTC).date() - timedelta(days=lookback_months * 30)
    memories = await store.list_memories(
        status=MemoryStatus.active.value,
        from_date=cutoff,
    )

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
        await store.save_profile(current_profile)
        profile = current_profile
    else:
        profile = TapestryProfile(
            content=content,
            generated_at=now,
            memory_count=len(memories),
        )
        await store.save_profile(profile)

    logger.info(
        "Profile generated (%d chars, %d memories)",
        len(content),
        len(memories),
    )
    return profile

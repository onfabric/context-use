from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_use.llm.base import LLMClient
from context_use.profile.generator import generate_profile
from context_use.profile.models import TapestryProfile
from context_use.profile.rules import RegenerationRule

logger = logging.getLogger(__name__)


async def _get_current_profile(
    tapestry_id: str,
    db: AsyncSession,
) -> TapestryProfile | None:
    result = await db.execute(
        select(TapestryProfile).where(
            TapestryProfile.tapestry_id == tapestry_id,
        )
    )
    return result.scalar_one_or_none()


async def trigger_profile_regeneration(
    tapestry_id: str,
    db: AsyncSession,
    llm_client: LLMClient,
    *,
    rules: list[RegenerationRule] | None = None,
    lookback_months: int = 6,
) -> TapestryProfile | None:
    """Check skip rules, then generate or regenerate the profile.

    Returns the profile if generated, or ``None`` if skipped.
    """
    if not tapestry_id:
        logger.debug("No tapestry_id — skipping profile regeneration")
        return None

    profile = await _get_current_profile(tapestry_id, db)

    for rule in rules or []:
        reason = await rule.should_skip(tapestry_id, profile, db)
        if reason:
            logger.info(
                "[%s] Skipping profile regeneration: %s",
                tapestry_id,
                reason,
            )
            return None

    return await generate_profile(
        tapestry_id,
        db,
        llm_client,
        current_profile=profile,
        lookback_months=lookback_months,
    )

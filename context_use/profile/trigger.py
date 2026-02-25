from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from context_use.models.profile import TapestryProfile
from context_use.profile.generator import generate_profile
from context_use.profile.rules import RegenerationRule

if TYPE_CHECKING:
    from context_use.llm.base import BaseLLMClient
    from context_use.store.base import Store

logger = logging.getLogger(__name__)


async def trigger_profile_regeneration(
    store: Store,
    llm_client: BaseLLMClient,
    *,
    rules: list[RegenerationRule] | None = None,
    lookback_months: int = 6,
) -> TapestryProfile | None:
    """Check skip rules, then generate or regenerate the profile.

    Returns the profile if generated, or ``None`` if skipped.
    """
    profile = await store.get_latest_profile()

    for rule in rules or []:
        reason = await rule.should_skip(profile, store)
        if reason:
            logger.info("Skipping profile regeneration: %s", reason)
            return None

    return await generate_profile(
        store,
        llm_client,
        current_profile=profile,
        lookback_months=lookback_months,
    )

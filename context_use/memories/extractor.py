from __future__ import annotations

import logging

from context_use.etl.models.thread import Thread
from context_use.llm.base import BatchResults, LLMClient, PromptItem
from context_use.memories.profile import ProfileContext
from context_use.memories.prompt import (
    MemoryPromptBuilder,
    MemorySchema,
)

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """Submit / poll wrapper for memory generation."""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def submit(
        self,
        batch_id: str,
        threads: list[Thread],
        profile: ProfileContext | None = None,
    ) -> str:
        """Build windowed prompts and submit as a batch job.

        Returns the ``job_key`` for polling.
        """
        builder = MemoryPromptBuilder(threads, profile=profile)
        prompts: list[PromptItem] = builder.build()
        logger.info(
            "[%s] Submitting %d window-prompts for %d threads",
            batch_id,
            len(prompts),
            len(threads),
        )
        return self.llm_client.batch_submit(batch_id, prompts)

    def get_results(
        self,
        job_key: str,
    ) -> BatchResults[MemorySchema] | None:
        """Poll for results. Returns ``None`` while still processing."""
        return self.llm_client.batch_get_results(job_key, MemorySchema)

from __future__ import annotations

import logging

from context_use.etl.models.thread import Thread
from context_use.llm.base import BatchResults, LLMClient, PromptItem
from context_use.memories.prompt import (
    MemoryPromptBuilder,
    MemorySchema,
)

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """Submit / poll wrapper for memory generation."""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    async def submit(self, batch_id: str, threads: list[Thread]) -> str:
        """Build day-grouped prompts and submit as a batch job.

        Returns the ``job_key`` for polling.
        """
        builder = MemoryPromptBuilder(threads)
        prompts: list[PromptItem] = builder.build()
        logger.info(
            "[%s] Submitting %d day-prompts for %d threads",
            batch_id,
            len(prompts),
            len(threads),
        )
        return await self.llm_client.batch_submit(batch_id, prompts)

    async def get_results(
        self,
        job_key: str,
    ) -> BatchResults[MemorySchema] | None:
        """Poll for results. Returns ``None`` while still processing."""
        return await self.llm_client.batch_get_results(job_key, MemorySchema)

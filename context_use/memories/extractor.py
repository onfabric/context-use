from __future__ import annotations

import logging

from context_use.etl.models.thread import Thread
from context_use.llm.base import BatchResults, LLMClient, PromptItem
from context_use.memories.prompt import (
    MemoryPromptBuilder,
    MemorySchema,
    WindowConfig,
)

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """Submit / poll wrapper for memory generation."""

    def __init__(
        self,
        llm_client: LLMClient,
        window_config: WindowConfig | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.window_config = window_config or WindowConfig()

    async def submit(self, batch_id: str, threads: list[Thread]) -> str:
        """Build window-grouped prompts and submit as a batch job.

        Returns the ``job_key`` for polling.
        """
        builder = MemoryPromptBuilder(threads, self.window_config)
        prompts: list[PromptItem] = builder.build()
        logger.info(
            "[%s] Submitting %d window-prompts for %d threads"
            " (window=%dd, overlap=%dd)",
            batch_id,
            len(prompts),
            len(threads),
            self.window_config.window_days,
            self.window_config.overlap_days,
        )
        return await self.llm_client.batch_submit(batch_id, prompts)

    async def get_results(
        self,
        job_key: str,
    ) -> BatchResults[MemorySchema] | None:
        """Poll for results. Returns ``None`` while still processing."""
        return await self.llm_client.batch_get_results(job_key, MemorySchema)

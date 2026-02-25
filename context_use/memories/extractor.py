from __future__ import annotations

import logging

from context_use.llm.base import BaseLLMClient, BatchResults, PromptItem
from context_use.memories.prompt import MemorySchema

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """Submit / poll wrapper for memory generation."""

    def __init__(self, llm_client: BaseLLMClient) -> None:
        self.llm_client = llm_client

    async def submit(self, batch_id: str, prompts: list[PromptItem]) -> str:
        """Submit pre-built prompts as a batch job.

        Returns the ``job_key`` for polling.
        """
        logger.info(
            "[%s] Submitting %d prompts",
            batch_id,
            len(prompts),
        )
        return await self.llm_client.batch_submit(batch_id, prompts)

    async def get_results(
        self,
        job_key: str,
    ) -> BatchResults[MemorySchema] | None:
        """Poll for results. Returns ``None`` while still processing."""
        return await self.llm_client.batch_get_results(job_key, MemorySchema)

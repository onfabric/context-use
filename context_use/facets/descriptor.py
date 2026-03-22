from __future__ import annotations

import logging

from context_use.facets.prompt import FacetDescriptionSchema
from context_use.llm.base import BaseLLMClient, BatchResults, PromptItem

logger = logging.getLogger(__name__)

MIN_FACET_MEMORY_COUNT = 5


class FacetDescriptor:
    def __init__(self, llm_client: BaseLLMClient) -> None:
        self._llm_client = llm_client

    async def submit(self, batch_id: str, prompts: list[PromptItem]) -> str:
        logger.info(
            "[%s] Submitting %d facet description prompts",
            batch_id,
            len(prompts),
        )
        return await self._llm_client.batch_submit(batch_id, prompts)

    async def get_results(
        self, job_key: str
    ) -> BatchResults[FacetDescriptionSchema] | None:
        return await self._llm_client.batch_get_results(job_key, FacetDescriptionSchema)

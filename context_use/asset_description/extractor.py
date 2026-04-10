from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from context_use.asset_description.prompt import AssetDescriptionSchema
from context_use.llm.base import BaseLLMClient, BatchResults, PromptItem

logger = logging.getLogger(__name__)

# Each prompt includes a base64-encoded image, making JSONL batch files
# impractically large.  We use concurrent structured_completion calls
# instead, with a semaphore to avoid overwhelming the API rate limit.
_MAX_CONCURRENCY = 10


class DescriptionExtractor(Protocol):
    async def submit(self, batch_id: str, prompts: list[PromptItem]) -> str: ...
    async def get_results(
        self, job_key: str
    ) -> BatchResults[AssetDescriptionSchema] | None: ...


class AssetDescriptionExtractor:
    """Default extractor using concurrent structured_completion calls."""

    def __init__(self, llm_client: BaseLLMClient) -> None:
        self._llm_client = llm_client
        self._cache: dict[str, BatchResults[AssetDescriptionSchema]] = {}

    async def submit(self, batch_id: str, prompts: list[PromptItem]) -> str:
        sem = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def _call(item: PromptItem) -> tuple[str, AssetDescriptionSchema | None]:
            async with sem:
                try:
                    result = await self._llm_client.structured_completion(
                        item, AssetDescriptionSchema
                    )
                    return item.item_id, result
                except Exception:
                    logger.error(
                        "Description generation failed for %s",
                        item.item_id,
                        exc_info=True,
                    )
                    return item.item_id, None

        pairs = await asyncio.gather(*[_call(p) for p in prompts])
        results: BatchResults[AssetDescriptionSchema] = {
            item_id: schema for item_id, schema in pairs if schema is not None
        }

        logger.info(
            "[%s] Completed %d/%d description extractions",
            batch_id,
            len(results),
            len(prompts),
        )

        key = f"gen-{batch_id}"
        self._cache[key] = results
        return key

    async def get_results(
        self, job_key: str
    ) -> BatchResults[AssetDescriptionSchema] | None:
        return self._cache.pop(job_key, None)

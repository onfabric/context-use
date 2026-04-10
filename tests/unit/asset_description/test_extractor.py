from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from context_use.asset_description.extractor import (
    _MAX_CONCURRENCY,
    AssetDescriptionExtractor,
)
from context_use.asset_description.prompt import AssetDescriptionSchema
from context_use.llm.base import PromptItem


def _make_prompt(item_id: str) -> PromptItem:
    return PromptItem(
        item_id=item_id,
        prompt="Describe this image.",
        asset_uris=["archive/pic.jpg"],
        response_schema=AssetDescriptionSchema.json_schema(),
    )


class TestAssetDescriptionExtractor:
    @pytest.mark.asyncio
    async def test_submit_and_get_results(self) -> None:
        client = AsyncMock()
        client.structured_completion.return_value = AssetDescriptionSchema(
            description="A cat on a roof"
        )

        extractor = AssetDescriptionExtractor(client)
        prompts = [_make_prompt("t1"), _make_prompt("t2")]
        job_key = await extractor.submit("batch-1", prompts)

        assert job_key == "gen-batch-1"
        assert client.structured_completion.call_count == 2

        results = await extractor.get_results(job_key)
        assert results is not None
        assert len(results) == 2
        assert results["t1"].description == "A cat on a roof"

    @pytest.mark.asyncio
    async def test_get_results_returns_none_after_pop(self) -> None:
        client = AsyncMock()
        client.structured_completion.return_value = AssetDescriptionSchema(
            description="test"
        )

        extractor = AssetDescriptionExtractor(client)
        job_key = await extractor.submit("b1", [_make_prompt("t1")])

        assert await extractor.get_results(job_key) is not None
        assert await extractor.get_results(job_key) is None

    @pytest.mark.asyncio
    async def test_individual_failure_does_not_crash_batch(self) -> None:
        client = AsyncMock()
        call_count = 0

        async def _side_effect(
            prompt: PromptItem, schema: type
        ) -> AssetDescriptionSchema:
            nonlocal call_count
            call_count += 1
            if prompt.item_id == "t2":
                raise RuntimeError("API error")
            return AssetDescriptionSchema(description="ok")

        client.structured_completion.side_effect = _side_effect

        extractor = AssetDescriptionExtractor(client)
        prompts = [_make_prompt("t1"), _make_prompt("t2"), _make_prompt("t3")]
        job_key = await extractor.submit("b1", prompts)
        results = await extractor.get_results(job_key)

        assert results is not None
        assert "t1" in results
        assert "t2" not in results
        assert "t3" in results

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self) -> None:
        client = AsyncMock()
        peak = 0
        current = 0
        lock = asyncio.Lock()

        async def _tracked(prompt: PromptItem, schema: type) -> AssetDescriptionSchema:
            nonlocal peak, current
            async with lock:
                current += 1
                if current > peak:
                    peak = current
            await asyncio.sleep(0.01)
            async with lock:
                current -= 1
            return AssetDescriptionSchema(description="ok")

        client.structured_completion.side_effect = _tracked

        extractor = AssetDescriptionExtractor(client)
        prompts = [_make_prompt(f"t{i}") for i in range(20)]
        await extractor.submit("b1", prompts)

        assert peak <= _MAX_CONCURRENCY

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from context_use.facets.descriptor import FacetDescriptor
from context_use.facets.prompt import FacetDescriptionSchema
from context_use.llm.base import PromptItem


def _make_llm(
    job_key: str = "job-abc",
    results: dict | None = None,
) -> MagicMock:
    llm = MagicMock()
    llm.batch_submit = AsyncMock(return_value=job_key)
    llm.batch_get_results = AsyncMock(return_value=results)
    return llm


def _make_prompt(item_id: str = "facet-1") -> PromptItem:
    return PromptItem(item_id=item_id, prompt="Describe this facet.")


async def test_submit_returns_job_key() -> None:
    llm = _make_llm(job_key="job-xyz")
    descriptor = FacetDescriptor(llm)

    key = await descriptor.submit("batch-1", [_make_prompt()])

    assert key == "job-xyz"
    llm.batch_submit.assert_awaited_once()


async def test_submit_passes_batch_id_and_prompts() -> None:
    llm = _make_llm()
    descriptor = FacetDescriptor(llm)
    prompts = [_make_prompt("f1"), _make_prompt("f2")]

    await descriptor.submit("batch-42", prompts)

    llm.batch_submit.assert_awaited_once_with("batch-42", prompts)


async def test_get_results_returns_none_while_pending() -> None:
    llm = _make_llm(results=None)
    descriptor = FacetDescriptor(llm)

    result = await descriptor.get_results("job-abc")

    assert result is None


async def test_get_results_returns_parsed_schema() -> None:
    schema = FacetDescriptionSchema(
        short_description="Alice is a close friend.",
        long_description="Alice is a long-time friend known for outdoor activities.",
    )
    llm = _make_llm(results={"facet-1": schema})
    descriptor = FacetDescriptor(llm)

    results = await descriptor.get_results("job-abc")

    assert results is not None
    assert results["facet-1"].short_description == "Alice is a close friend."

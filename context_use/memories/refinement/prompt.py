from __future__ import annotations

from pydantic import BaseModel, Field

from context_use.llm.base import PromptItem
from context_use.memories.models import TapestryMemory

REFINEMENT_SYSTEM_PROMPT = """\
You are a memory refinement assistant. You receive a cluster of related memories \
about a person's life, extracted from different sources or time periods.

Your job is to produce a refined set of memories that:

1. **Merge** complementary memories about the same event or topic into a single, \
richer memory.
2. **Resolve conflicts** — when memories contradict each other, prefer the one \
with a more recent date range (from_date/to_date). If dates are identical, \
keep both perspectives.
3. **Keep separate** memories that describe genuinely distinct events, even if \
they are semantically similar.
4. **Preserve temporal accuracy** — each output memory must have correct \
from_date and to_date values. When merging, use the earliest from_date and \
latest to_date of the inputs.
5. **Do not fabricate** details not present in the input memories.
6. **Track sources** — for each output memory, list the IDs of the input \
memories it was derived from in the source_ids field.

Output memories should be vivid and detail-rich, in first person, 1-3 sentences each.
"""


class RefinedMemory(BaseModel):
    """A single refined memory produced by the LLM."""

    content: str = Field(description="A vivid, detail-rich memory in 1-3 sentences")
    from_date: str = Field(description="Start date (YYYY-MM-DD)")
    to_date: str = Field(description="End date (YYYY-MM-DD)")
    source_ids: list[str] = Field(
        description="IDs of input memories this was derived from"
    )


class RefinementSchema(BaseModel):
    """Top-level response the LLM should return per cluster."""

    memories: list[RefinedMemory] = Field(
        description="Refined memories for this cluster"
    )

    @classmethod
    def json_schema(cls) -> dict:
        return cls.model_json_schema()


def build_refinement_prompt(
    cluster_id: str,
    memories: list[TapestryMemory],
) -> PromptItem:
    """Build a PromptItem for refining a cluster of memories."""
    lines: list[str] = [REFINEMENT_SYSTEM_PROMPT, "", "## Input memories", ""]

    for m in sorted(memories, key=lambda x: x.from_date):
        lines.append(
            f"- **ID**: {m.id}\n"
            f"  **Date range**: {m.from_date.isoformat()} to {m.to_date.isoformat()}\n"
            f"  **Content**: {m.content}"
        )
        lines.append("")

    lines.append(
        "Produce the refined set of memories. "
        "Every input memory must appear in at least one output's source_ids."
    )

    return PromptItem(
        item_id=cluster_id,
        prompt="\n".join(lines),
        response_schema=RefinementSchema.json_schema(),
    )

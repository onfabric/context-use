from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from context_use.facets.types import FacetType
from context_use.llm.base import PromptItem
from context_use.models.thread import Thread


class MemoryFacetExtract(BaseModel):
    facet_type: FacetType = Field(
        description="Category of the facet — must be one of the defined facet types"
    )
    facet_value: str = Field(description=("Extracted facet value"))


class Memory(BaseModel):
    """A single memory produced by the LLM."""

    content: str = Field(description="A vivid, detail-rich memory in 1-2 sentences")
    from_date: str = Field(description="Start date of the memory (YYYY-MM-DD)")
    to_date: str = Field(
        description=(
            "End date of the memory (YYYY-MM-DD, same as from_date for single-day)"
        )
    )
    facets: list[MemoryFacetExtract] = Field(
        default_factory=list,
        description="Semantic facets extracted from this memory",
    )


class MemorySchema(BaseModel):
    """Top-level response the LLM should return per window."""

    memories: list[Memory] = Field(description="List of memories for this period")

    @classmethod
    def json_schema(cls) -> dict:
        return cls.model_json_schema()


@dataclass
class GroupContext:
    """Everything the prompt builder needs for one group."""

    group_id: str
    new_threads: list[Thread]
    prior_memories: list[str] = field(default_factory=list)
    recent_threads: list[Thread] = field(default_factory=list)
    user_profile: str | None = None


class BasePromptBuilder(ABC):
    """Strategy interface for building an LLM prompt from a single group.

    Each provider / interaction type supplies its own subclass that knows
    how to format threads into a prompt and determine whether the group
    has enough content to process.
    """

    def __init__(self, context: GroupContext) -> None:
        self.context = context

    @abstractmethod
    def build(self) -> PromptItem:
        """Return a ``PromptItem`` for this group."""
        ...

    @staticmethod
    def _format_context(ctx: GroupContext) -> str:
        """Build an optional context preamble from user profile, prior memories,
        and recent threads.

        Returns an empty string when there is no prior context (initial run),
        keeping the prompt identical to the non-delta path.
        """
        if not ctx.user_profile and not ctx.prior_memories and not ctx.recent_threads:
            return ""

        sections: list[str] = []

        if ctx.user_profile:
            sections.append(
                "## User profile\n"
                "High-level context about the user. Use this to frame and "
                "personalise the memories you extract — do not repeat it as "
                "a memory itself.\n\n"
                f"{ctx.user_profile.strip()}"
            )

        if ctx.prior_memories:
            memories_text = "\n".join(f"- {m}" for m in ctx.prior_memories)
            sections.append(
                "## Previously extracted memories\n"
                "These memories have already been extracted from earlier "
                "interactions. Use them for continuity but do NOT repeat "
                "or rephrase them — only produce NEW memories from the "
                "new messages below.\n\n"
                f"{memories_text}"
            )

        if ctx.recent_threads:
            lines: list[str] = []
            for t in sorted(ctx.recent_threads, key=lambda t: t.asat):
                ts = t.asat.strftime("%H:%M")
                lines.append(f"- [{ts}] {t.preview}")
            sections.append(
                "## Recent messages (for context only — already processed)\n"
                + "\n".join(lines)
            )

        return "\n\n".join(sections) + "\n\n"

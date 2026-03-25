from __future__ import annotations

from collections import defaultdict
from datetime import date

from context_use.facets.types import render_facet_types_section
from context_use.llm.base import PromptItem
from context_use.memories.prompt.base import BasePromptBuilder, MemorySchema
from context_use.models.thread import Thread

_FACETS_SECTION = render_facet_types_section()

SEARCH_MEMORIES_PROMPT = (
    """\
You are given a user's Google search history from **{{FROM_DATE}}** to \
**{{TO_DATE}}**, grouped by day.

## Your task

Identify **recurring themes**: groups of related searches that together \
suggest the user was actively exploring a topic, making a decision, or \
dealing with a life situation across **multiple different days**.

A single isolated search is noise. A pattern that repeats or evolves \
over several days is signal.

### When to create a memory

Only create a memory when:
- The same or closely related topic appears on **at least two different days**.
- The cluster of searches points to something concrete in the user's life \
(planning a trip, exploring a health concern, learning a skill, making a \
purchase, job hunting, etc.).

### When not to create a memory

Skip:
- One-off searches with no follow-up on other days.
- Generic lookups with no personal signal (weather, time zones, unit \
conversions, sports scores, basic factual questions).
- Topics that appear on a single day even if searched multiple times that day.

### How to write memories

- Write from the user's perspective, as a first-person statement.
- Describe the apparent situation or interest — not a list of the searches.
- Be honest about uncertainty: prefer "I seemed to be looking into", \
"I was exploring", "I appeared to be interested in" over stating intent \
as fact.
- Do not fabricate details beyond what the searches suggest.
- Use the **earliest date** the pattern appears as ``from_date`` and the \
**latest date** as ``to_date``.

It is correct — and often right — to return **zero memories** if there \
is no clear multi-day pattern.

{{CONTEXT}}\
## Searches

{{SEARCHES}}

## Output format
Return a JSON object with a ``memories`` array. Each memory has:
- ``content``: the memory text (1-2 sentences, first-person, \
describes a pattern not individual searches).
- ``from_date``: earliest date the pattern appeared (YYYY-MM-DD).
- ``to_date``: latest date the pattern appeared (YYYY-MM-DD).
- ``facets``: an array of semantic facets extracted from the memory. \
Each facet has:
  - ``facet_type``: one of the types defined below.
  - ``facet_value``: the specific extracted value.
"""
    + _FACETS_SECTION
)


class GoogleSearchMemoryPromptBuilder(BasePromptBuilder):
    """Builds memory prompts for Google search history windows."""

    def build(self) -> PromptItem:
        threads = sorted(self.context.new_threads, key=lambda t: t.asat)
        from_date = threads[0].asat.date()
        to_date = threads[-1].asat.date()
        searches_block = self._format_searches(threads)
        context_block = self._format_context(self.context)

        prompt = (
            SEARCH_MEMORIES_PROMPT.replace("{{FROM_DATE}}", from_date.isoformat())
            .replace("{{TO_DATE}}", to_date.isoformat())
            .replace("{{CONTEXT}}", context_block)
            .replace("{{SEARCHES}}", searches_block)
        )

        return PromptItem(
            item_id=self.context.group_id,
            prompt=prompt,
            response_schema=MemorySchema.json_schema(),
        )

    @staticmethod
    def _format_searches(threads: list[Thread]) -> str:
        by_day: dict[date, list[Thread]] = defaultdict(list)
        for t in threads:
            by_day[t.asat.date()].append(t)

        sections: list[str] = []
        for day, day_threads in sorted(by_day.items()):
            lines = [f"### {day.isoformat()}"]
            for t in sorted(day_threads, key=lambda t: t.asat):
                ts = t.asat.strftime("%H:%M")
                lines.append(f"- [{ts}] {t.preview}")
            sections.append("\n".join(lines))

        return "\n\n".join(sections)

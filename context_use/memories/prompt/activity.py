from __future__ import annotations

from collections import defaultdict
from datetime import date

from context_use.batch.grouper import WindowConfig
from context_use.llm.base import PromptItem
from context_use.memories.prompt.base import (
    BasePromptBuilder,
    GroupContext,
    MemorySchema,
)
from context_use.models.thread import Thread
from context_use.prompt_categories import WHAT_TO_CAPTURE

ACTIVITY_MEMORIES_PROMPT = (
    """\
You are given a chronological log of a user's activities from \
**{{FROM_DATE}}** to **{{TO_DATE}}**, grouped by day. Each entry has a \
timestamp and a text description of what the user did — searches they \
performed, places they booked or saved, reviews they wrote, etc.

## Your task

Extract the user's **memories** from this activity log. A memory is a \
vivid, first-person account of something the user did, planned, \
experienced, or decided — written as if the user is journaling about \
their life.

**Reason across all entries.** Activities on different days may be \
related — searches for the same destination followed by a booking \
signal a trip; multiple saves to the same wishlist signal planning. \
Connect the dots to produce richer memories.

"""
    + WHAT_TO_CAPTURE
    + """

### Granularity

Let the data guide you:
- A single notable activity → single-day memory.
- A cluster of related activities (e.g. searching then booking a trip) \
→ one memory spanning the relevant dates.
- Repetitive low-signal entries (many near-identical searches) → \
summarise the intent, don't list every search.

Generate between {{MIN_MEMORIES}} and {{MAX_MEMORIES}} memories.

### Detail level

Each memory should be **information-dense**:
- Include specific place names, cities, neighbourhoods, venues.
- Note dates, durations, number of guests when available.
- Capture the user's intent (why they searched, what they booked).
- Preserve ratings, opinions, and preferences from reviews.
- Include any details that reveal travel style, taste, or priorities.

### What to avoid

- Do not fabricate details not present in the log entries.
- Do not write filler ("explored some options", "did some searching").
- Do not narrate the medium ("in my search history") — describe the \
experience or intent.
- Do not produce one memory per log entry — synthesise related entries.

{{CONTEXT}}\
{{ACTIVITIES}}

## Output format
Return a JSON object with a ``memories`` array. Each memory has:
- ``content``: the memory text (1-2 sentences, detail-rich, first-person).
- ``from_date``: start date (YYYY-MM-DD).
- ``to_date``: end date (YYYY-MM-DD, same as from_date for single-day).
"""
)


class ActivityMemoryPromptBuilder(BasePromptBuilder):
    """Build one ``PromptItem`` per time-window group from text-only activity threads.

    Unlike ``MediaMemoryPromptBuilder`` which requires image assets, this
    builder works with any thread that has a text preview — searches,
    bookings, reviews, saves, etc.
    """

    def __init__(
        self,
        contexts: list[GroupContext],
        config: WindowConfig | None = None,
    ) -> None:
        super().__init__(contexts)
        self.config = config or WindowConfig()

    def has_content(self) -> bool:
        return any(ctx.new_threads for ctx in self.contexts)

    def build(self) -> list[PromptItem]:
        response_schema = MemorySchema.json_schema()

        items: list[PromptItem] = []
        for ctx in self.contexts:
            if not ctx.new_threads:
                continue

            sorted_threads = sorted(ctx.new_threads, key=lambda t: t.asat)
            from_date = sorted_threads[0].asat.date()
            to_date = sorted_threads[-1].asat.date()
            activities_block = self._format_activities(sorted_threads)
            context_block = self._format_context(ctx)

            prompt = (
                ACTIVITY_MEMORIES_PROMPT.replace(
                    "{{FROM_DATE}}", from_date.isoformat()
                )
                .replace("{{TO_DATE}}", to_date.isoformat())
                .replace("{{CONTEXT}}", context_block)
                .replace("{{ACTIVITIES}}", activities_block)
                .replace(
                    "{{MIN_MEMORIES}}",
                    str(self.config.effective_min_memories),
                )
                .replace(
                    "{{MAX_MEMORIES}}",
                    str(self.config.effective_max_memories),
                )
            )

            items.append(
                PromptItem(
                    item_id=ctx.group_id,
                    prompt=prompt,
                    response_schema=response_schema,
                )
            )
        return items

    @staticmethod
    def _format_activities(threads: list[Thread]) -> str:
        by_day: dict[date, list[Thread]] = defaultdict(list)
        for t in threads:
            by_day[t.asat.date()].append(t)

        multi_day = len(by_day) > 1
        sections: list[str] = []

        for day, day_threads in sorted(by_day.items()):
            lines: list[str] = []
            if multi_day:
                lines.append(f"### {day.isoformat()}")
            for t in sorted(day_threads, key=lambda t: t.asat):
                ts = t.asat.strftime("%H:%M")
                lines.append(f"- [{ts}] {t.preview}")
            sections.append("\n".join(lines))

        return "## Activity log\n\n" + "\n\n".join(sections)

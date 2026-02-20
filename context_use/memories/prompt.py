from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from pydantic import BaseModel, Field

from context_use.batch.grouper import WindowConfig, decode_window_key
from context_use.etl.models.thread import Thread
from context_use.llm.base import PromptItem


class Memory(BaseModel):
    """A single memory produced by the LLM."""

    content: str = Field(description="A vivid, detail-rich memory in 1-2 sentences")
    from_date: str = Field(description="Start date of the memory (YYYY-MM-DD)")
    to_date: str = Field(
        description=(
            "End date of the memory (YYYY-MM-DD, same as from_date for single-day)"
        )
    )


class MemorySchema(BaseModel):
    """Top-level response the LLM should return per window."""

    memories: list[Memory] = Field(description="List of memories for this period")

    @classmethod
    def json_schema(cls) -> dict:
        return cls.model_json_schema()


@dataclass
class GroupContext:
    """Everything the prompt builder needs for one group.

    For the initial (static archive) run, only ``group_key`` and
    ``new_threads`` are populated.  The ``prior_memories`` and
    ``recent_threads`` fields are used by the delta path (hosted)
    to give the LLM context from previously processed data.
    """

    group_key: str
    new_threads: list[Thread]
    prior_memories: list[str] = field(default_factory=list)
    recent_threads: list[Thread] = field(default_factory=list)


MEMORIES_PROMPT = """\
You are given social-media posts from **{{FROM_DATE}}** to \
**{{TO_DATE}}**, grouped by day. Each post includes a timestamp and a \
text preview, and may have an attached image or video (labelled [Image N]).

## Your task

Extract the user's **memories** from this period. A memory is a vivid, \
first-person account of something the user did, experienced, or felt — \
written as if the user is journaling about their life.

**Study every image carefully.** The images are your richest source of \
detail. Read all visible text (signs, screens, menus, name badges, \
whiteboards). Note brands, logos, UI on screens, food on plates, people \
in the frame, and anything that reveals where the user was or what they \
were doing.

Then reason across **all** posts in the window. Posts from different \
days may be related — a location visible in one image may explain a \
caption from another day, or repeated appearances of the same people or \
places may signal a multi-day event. Connect the dots.

### Granularity

Let the data guide you:
- A specific moment (a meal, a selfie) → single-day memory.
- A recurring theme or multi-day event (a work sprint, a trip) → memory \
spanning the relevant dates.
- The same post can feed multiple memories at different granularities.

Generate between {{MIN_MEMORIES}} and {{MAX_MEMORIES}} memories.

### Detail level

Each memory should be **information-dense**. Pack in every observable \
detail that says something about the user's life:
- Specific food items and ingredients, not just "a sandwich".
- Venue names, street signs, neighbourhood, city — not just "an office".
- What is on their screen: language, framework, project name, file names.
- Who is around: number of people, what they are doing, any names/tags.
- Clothing, accessories, hairstyle — these reveal personal style over \
time.
- Time-of-day context when it adds meaning (morning routine vs late \
night).

### What to avoid

- Do not fabricate details that are not visible or stated.
- Do not write filler ("had a nice day", "as seen in the photo").
- Do not narrate the medium ("in my Instagram story") — describe the \
experience, not the post.

{{CONTEXT}}\
{{POSTS}}

## Output format
Return a JSON object with a ``memories`` array. Each memory has:
- ``content``: the memory text (1-2 sentences, detail-rich).
- ``from_date``: start date (YYYY-MM-DD).
- ``to_date``: end date (YYYY-MM-DD, same as from_date for single-day).
"""


class MemoryPromptBuilder:
    """Build one ``PromptItem`` per group from a list of GroupContexts."""

    def __init__(
        self,
        contexts: list[GroupContext],
        config: WindowConfig | None = None,
    ) -> None:
        self.contexts = contexts
        self.config = config or WindowConfig()

    def build(self) -> list[PromptItem]:
        response_schema = MemorySchema.json_schema()

        items: list[PromptItem] = []
        for ctx in self.contexts:
            threads_with_assets = [
                t for t in ctx.new_threads if t.asset_uri is not None
            ]
            if not threads_with_assets:
                continue

            from_date, to_date = decode_window_key(ctx.group_key)
            posts_block, asset_paths = self._format_posts(threads_with_assets)
            context_block = self._format_context(ctx)

            prompt = (
                MEMORIES_PROMPT.replace("{{FROM_DATE}}", from_date.isoformat())
                .replace("{{TO_DATE}}", to_date.isoformat())
                .replace("{{CONTEXT}}", context_block)
                .replace("{{POSTS}}", posts_block)
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
                    item_id=ctx.group_key,
                    prompt=prompt,
                    response_schema=response_schema,
                    asset_paths=asset_paths,
                )
            )
        return items

    @staticmethod
    def _format_context(ctx: GroupContext) -> str:
        """Build an optional context preamble from prior memories / recent threads.

        Returns an empty string when there is no prior context (initial run),
        keeping the prompt identical to the non-delta path.
        """
        if not ctx.prior_memories and not ctx.recent_threads:
            return ""

        sections: list[str] = []

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

    @staticmethod
    def _format_posts(
        threads: list[Thread],
    ) -> tuple[str, list[str]]:
        """Format threads with timestamps, grouped by day when needed.

        When the window spans multiple days, threads are grouped under
        ``### YYYY-MM-DD`` sub-headers.  For single-day windows the
        sub-header is omitted (the date is already in the prompt).

        Returns ``(text_block, asset_paths)`` where images in
        *asset_paths* are in the same order as ``[Image N]`` labels
        in *text_block*.
        """
        by_day: dict[date, list[Thread]] = defaultdict(list)
        for t in threads:
            by_day[t.asat.date()].append(t)

        multi_day = len(by_day) > 1
        sections: list[str] = []
        asset_paths: list[str] = []
        img_idx = 0

        for day, day_threads in sorted(by_day.items()):
            lines: list[str] = []
            if multi_day:
                lines.append(f"### {day.isoformat()}")
            for t in sorted(day_threads, key=lambda t: t.asat):
                ts = t.asat.strftime("%H:%M")
                if t.asset_uri:
                    img_idx += 1
                    lines.append(f"- [{ts}] [Image {img_idx}] {t.preview}")
                    asset_paths.append(t.asset_uri)
                else:
                    lines.append(f"- [{ts}] {t.preview}")
            sections.append("\n".join(lines))

        return "\n\n".join(sections), asset_paths

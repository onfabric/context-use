from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from pydantic import BaseModel, Field

from context_use.etl.models.thread import Thread
from context_use.llm.base import PromptItem


@dataclass(frozen=True)
class WindowConfig:
    """Controls the sliding-window used to group interactions into prompts.

    Defaults reproduce the legacy 1-day / no-overlap behaviour.
    """

    window_days: int = 5
    overlap_days: int = 1
    max_memories: int | None = None
    min_memories: int | None = None

    def __post_init__(self) -> None:
        if self.overlap_days >= self.window_days:
            raise ValueError("overlap_days must be smaller than window_days")

    @property
    def step_days(self) -> int:
        return self.window_days - self.overlap_days

    @property
    def effective_max_memories(self) -> int:
        if self.max_memories is not None:
            return self.max_memories
        return max(5, self.window_days * 3)

    @property
    def effective_min_memories(self) -> int:
        if self.min_memories is not None:
            return self.min_memories
        return max(1, self.window_days)


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

{{POSTS}}

## Output format
Return a JSON object with a ``memories`` array. Each memory has:
- ``content``: the memory text (1-2 sentences, detail-rich).
- ``from_date``: start date (YYYY-MM-DD).
- ``to_date``: end date (YYYY-MM-DD, same as from_date for single-day).
"""


def _compute_windows(
    threads: list[Thread],
    config: WindowConfig,
) -> list[tuple[date, date, list[Thread]]]:
    """Produce ``(window_start, window_end, threads)`` tuples."""
    if not threads:
        return []

    sorted_threads = sorted(threads, key=lambda t: t.asat)
    min_date = sorted_threads[0].asat.date()
    max_date = sorted_threads[-1].asat.date()

    windows: list[tuple[date, date, list[Thread]]] = []
    window_start = min_date

    while window_start <= max_date:
        window_end = window_start + timedelta(days=config.window_days - 1)
        window_threads = [
            t for t in sorted_threads if window_start <= t.asat.date() <= window_end
        ]
        if window_threads:
            windows.append((window_start, window_end, window_threads))
        window_start += timedelta(days=config.step_days)

    return windows


def encode_window_key(from_date: date, to_date: date) -> str:
    return f"{from_date.isoformat()}/{to_date.isoformat()}"


def decode_window_key(key: str) -> tuple[date, date]:
    from_str, to_str = key.split("/")
    return date.fromisoformat(from_str), date.fromisoformat(to_str)


class MemoryPromptBuilder:
    """Build one ``PromptItem`` per window from a flat list of threads."""

    def __init__(
        self,
        threads: list[Thread],
        config: WindowConfig | None = None,
    ) -> None:
        self.threads = [t for t in threads if t.asset_uri is not None]
        self.config = config or WindowConfig()

    def build(self) -> list[PromptItem]:
        windows = _compute_windows(self.threads, self.config)
        response_schema = MemorySchema.json_schema()

        items: list[PromptItem] = []
        for window_start, window_end, window_threads in windows:
            posts_block, asset_paths = self._format_posts(window_threads)
            prompt = (
                MEMORIES_PROMPT.replace("{{FROM_DATE}}", window_start.isoformat())
                .replace("{{TO_DATE}}", window_end.isoformat())
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
                    item_id=encode_window_key(window_start, window_end),
                    prompt=prompt,
                    response_schema=response_schema,
                    asset_paths=asset_paths,
                )
            )
        return items

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

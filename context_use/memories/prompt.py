"""Prompt template and schemas for memory generation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from pydantic import BaseModel, Field

from context_use.etl.models.thread import Thread
from context_use.llm.base import PromptItem
from context_use.memories.profile import ProfileContext

DEFAULT_WINDOW_DAYS = 7
DEFAULT_STRIDE_DAYS = 5


class Memory(BaseModel):
    """A single memory produced by the LLM."""

    content: str = Field(description="A short, meaningful memory in 1-2 sentences")
    from_date: str = Field(description="Start date in YYYY-MM-DD format")
    to_date: str = Field(
        description=(
            "End date in YYYY-MM-DD format (same as from_date for single-day memories)"
        )
    )


class MemorySchema(BaseModel):
    """Top-level response the LLM should return per window of posts."""

    memories: list[Memory] = Field(description="List of memories for this period")

    @classmethod
    def json_schema(cls) -> dict:
        return cls.model_json_schema()

    @classmethod
    def format_schema_for_prompt(cls) -> str:
        schema = cls.model_json_schema()
        lines = []
        for name, prop in schema.get("properties", {}).items():
            lines.append(f"- `{name}`: {prop.get('description', '')}")
        return "\n".join(lines)


PROFILE_PREAMBLE = """\
## User reference

[Image 1] is a reference photo of the user whose memories you are generating.
Use it to identify the user in the posts below.

When the user appears in a post, write the memory from their first-person
perspective. Describe everything you can observe about the scene:

- **What the user is doing**: eating, coding, presenting, walking, posing, etc.
- **Appearance & clothing**: outfit, accessories, hairstyle — these reveal
  personal style.
- **Food & drink**: specific dishes, ingredients visible on the plate, brand
  of coffee cup, type of drink.
- **People**: how many, what they are doing, any visible name tags, @-mentions
  in captions.
- **Location & setting**: venue names, signage, logos, decor, neighbourhood
  cues, geotags, hashtags.
- **Screens & work**: what is on a monitor or whiteboard — programming
  language, diagrams, project names.

The goal is to capture enough detail that these memories can later reveal the
user's preferences, habits, and lifestyle. Be specific, not generic.

For example, instead of:
  "Enjoyed a meal at a restaurant with friends."
Write:
  "I had a bacon cheeseburger with pickles and caramelised onions at Five
   Guys on Wardour Street with @jake and @maria."

"""

MEMORIES_PROMPT = """\
You are given social-media posts from **{{FROM_DATE}}** to **{{TO_DATE}}**, \
grouped by day. Each post includes a timestamp and a text preview, and may \
have an attached image or video (labelled [Image N]).

## Your task

Extract the user's **memories** from this period. A memory is a vivid, \
first-person account of something the user did, experienced, or felt — \
written as if the user is journaling about their life.

**Study every image carefully.** The images are your richest source of \
detail. Read all visible text (signs, screens, menus, name badges, \
whiteboards). Note brands, logos, UI on screens, food on plates, people \
in the frame, and anything that reveals where the user was or what they \
were doing.

Then reason across **all** posts in the window. Posts from different days \
may be related — a location visible in one image may explain a caption \
from another day, or repeated appearances of the same people or places \
may signal a multi-day event. Connect the dots.

### Granularity

Let the data guide you:
- A specific moment (a meal, a selfie) → single-day memory.
- A recurring theme or multi-day event (a work sprint, a trip) → memory \
spanning the relevant dates.
- The same post can feed multiple memories at different granularities.

### Detail level

Each memory should be **information-dense**. Pack in every observable \
detail that says something about the user's life:
- Specific food items and ingredients, not just "a sandwich".
- Venue names, street signs, neighbourhood, city — not just "an office".
- What is on their screen: language, framework, project name, file names.
- Who is around: number of people, what they are doing, any names/tags.
- Clothing, accessories, hairstyle — these reveal personal style over time.
- Time-of-day context when it adds meaning (morning routine vs late night).

**Bad:** "I was at an office working on code."
**Good:** "I spent the afternoon at the Fabric office on the 3rd floor, \
pair-programming in Python on a memory-bank pipeline with two teammates, \
using an ultrawide monitor."

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


class MemoryPromptBuilder:
    """Build one ``PromptItem`` per rolling window from a flat list of threads.

    Windows default to ``DEFAULT_WINDOW_DAYS`` days with a stride of
    ``DEFAULT_STRIDE_DAYS`` days, so adjacent windows overlap and the same
    post can inform memories in more than one window.
    """

    def __init__(
        self,
        threads: list[Thread],
        profile: ProfileContext | None = None,
        window_days: int = DEFAULT_WINDOW_DAYS,
        stride_days: int = DEFAULT_STRIDE_DAYS,
    ) -> None:
        self.threads = [t for t in threads if t.asset_uri is not None]
        self.profile = profile
        self.window_days = window_days
        self.stride_days = stride_days

    def build(self) -> list[PromptItem]:
        by_day: dict[date, list[Thread]] = defaultdict(list)
        for t in self.threads:
            by_day[t.asat.date()].append(t)

        if not by_day:
            return []

        all_days = sorted(by_day)
        windows = self._rolling_windows(all_days[0], all_days[-1])

        response_schema = MemorySchema.json_schema()

        has_profile = self.profile is not None
        img_start = 2 if has_profile else 1

        items: list[PromptItem] = []
        for win_start, win_end in windows:
            window_threads = {
                d: threads for d, threads in by_day.items() if win_start <= d <= win_end
            }
            if not window_threads:
                continue

            posts_block, asset_paths = self._format_window_posts(
                window_threads, img_start=img_start
            )

            prompt = MEMORIES_PROMPT
            if has_profile:
                prompt = PROFILE_PREAMBLE + prompt
                asset_paths = [self.profile.face_image_path] + asset_paths  # type: ignore[union-attr]

            prompt = (
                prompt.replace("{{FROM_DATE}}", win_start.isoformat())
                .replace("{{TO_DATE}}", win_end.isoformat())
                .replace("{{POSTS}}", posts_block)
            )

            item_id = f"{win_start.isoformat()}..{win_end.isoformat()}"
            items.append(
                PromptItem(
                    item_id=item_id,
                    prompt=prompt,
                    response_schema=response_schema,
                    asset_paths=asset_paths,
                )
            )
        return items

    def _rolling_windows(
        self, min_date: date, max_date: date
    ) -> list[tuple[date, date]]:
        """Generate ``(start, end)`` pairs for each rolling window."""
        windows: list[tuple[date, date]] = []
        start = min_date
        while start <= max_date:
            end = start + timedelta(days=self.window_days - 1)
            windows.append((start, min(end, max_date)))
            start += timedelta(days=self.stride_days)
        return windows

    @staticmethod
    def _format_window_posts(
        by_day: dict[date, list[Thread]], img_start: int = 1
    ) -> tuple[str, list[str]]:
        """Format posts grouped by day with sub-headings and timestamps."""
        lines: list[str] = []
        asset_paths: list[str] = []
        img_idx = img_start
        for day in sorted(by_day):
            lines.append(f"\n### {day.isoformat()}")
            for t in sorted(by_day[day], key=lambda t: t.asat):
                time_str = t.asat.strftime("%H:%M UTC")
                if t.asset_uri:
                    lines.append(f"- ({time_str}) [Image {img_idx}] {t.preview}")
                    asset_paths.append(t.asset_uri)
                    img_idx += 1
                else:
                    lines.append(f"- ({time_str}) {t.preview}")
        return "\n".join(lines), asset_paths

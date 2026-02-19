"""Prompt template and schemas for memory generation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from pydantic import BaseModel, Field

from context_use.etl.models.thread import Thread
from context_use.llm.base import PromptItem
from context_use.memories.profile import ProfileContext


class Memory(BaseModel):
    """A single memory produced by the LLM."""

    content: str = Field(description="A short, meaningful memory in 1-2 sentences")


class MemorySchema(BaseModel):
    """Top-level response the LLM should return per day."""

    memories: list[Memory] = Field(description="List of memories for this day")

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
perspective. Describe only what is directly visible or stated: what the user
is doing, eating, drinking, or wearing, who they are with, and what those
people are doing. Do not infer emotions or relationships beyond what the
data shows. Ignore irrelevant background details.

Always preserve any concrete evidence of where the user was and who they were
with: location names, venue names, tagged people, @-mentions, geotags,
hashtags, and any visible signage or branding in the images.

For example, instead of:
  "Enjoyed a meal at a restaurant with friends."
Write:
  "I had a bacon cheeseburger at Five Guys with @jake and @maria."

These personal details will be used to learn the user's preferences, habits,
and lifestyle over time.

"""

MEMORIES_PROMPT = """\
You are given a collection of social-media posts from a single day.
Each post has a text preview and may include an attached image or video
(sent as a preceding media part labelled [Image N] in the post list).

Your task is to identify the meaningful **memories** from this day.
A memory is a 1-2 sentence summary that captures something personally
significant — an event, an experience, or an emotional moment.
Use both the text previews and the visual content of any attached media to
inform your understanding.

**Only state what is directly observable or explicitly mentioned in the data.**
Do not guess, infer ownership, or assume relationships unless there is clear
evidence (e.g. a caption, tag, or repeated pattern). For instance, a photo
of the user holding a cat means "I was at an office", not "I was at my office"
— unless the caption or tags confirm it is the user's office.

Focus on what the user did, experienced, or felt. Include specific details
that reveal preferences or habits (e.g. what they ate, where they went, who
they were with). Skip generic background descriptions that don't say anything
about the user.

Generate between 1 and 5 memories.

## Posts from {{DATE}}

{{POSTS}}

## Output Format
Return a JSON object with the following structure:
{{SCHEMA}}"""


class MemoryPromptBuilder:
    """Build one ``PromptItem`` per day from a flat list of threads."""

    def __init__(
        self,
        threads: list[Thread],
        profile: ProfileContext | None = None,
    ) -> None:
        self.threads = [t for t in threads if t.asset_uri is not None]
        self.profile = profile

    def build(self) -> list[PromptItem]:
        by_day: dict[date, list[Thread]] = defaultdict(list)
        for t in self.threads:
            by_day[t.asat.date()].append(t)

        schema_text = MemorySchema.format_schema_for_prompt()
        response_schema = MemorySchema.json_schema()

        has_profile = self.profile is not None
        img_start = 2 if has_profile else 1

        items: list[PromptItem] = []
        for day, day_threads in sorted(by_day.items()):
            posts_block, asset_paths = self._format_posts(
                day_threads, img_start=img_start
            )

            prompt = MEMORIES_PROMPT
            if has_profile:
                prompt = PROFILE_PREAMBLE + prompt
                asset_paths = [self.profile.face_image_path] + asset_paths  # type: ignore[union-attr]

            prompt = (
                prompt.replace("{{DATE}}", day.isoformat())
                .replace("{{POSTS}}", posts_block)
                .replace("{{SCHEMA}}", schema_text)
            )
            items.append(
                PromptItem(
                    item_id=day.isoformat(),
                    prompt=prompt,
                    response_schema=response_schema,
                    asset_paths=asset_paths,
                )
            )
        return items

    @staticmethod
    def _format_posts(
        threads: list[Thread], img_start: int = 1
    ) -> tuple[str, list[str]]:
        """Return ``(text_block, asset_paths)`` for a day's threads."""
        lines: list[str] = []
        asset_paths: list[str] = []
        img_idx = img_start
        for t in threads:
            if t.asset_uri:
                lines.append(f"- [Image {img_idx}] {t.preview}")
                asset_paths.append(t.asset_uri)
                img_idx += 1
            else:
                lines.append(f"- {t.preview}")
        return "\n".join(lines), asset_paths

"""Prompt template and schemas for memory generation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from pydantic import BaseModel, Field

from context_use.etl.models.thread import Thread
from context_use.llm.base import PromptItem


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


MEMORIES_PROMPT = """\
You are given a collection of social-media posts from a single day.
Each post has a text preview and may include an attached image or video
(sent as a preceding media part labelled [Image N] in the post list).

Your task is to identify the meaningful **memories** from this day.
A memory is a concise 1-2 sentence summary that captures something personally
significant — an event, an experience, or an emotional moment.
Use both the text previews and the visual content of any attached media to
inform your understanding.

Describe the memories in detail so that they are necessary for these to be usable as
context for a LLM that wants to answer questions about the user's life and preferences.

Generate between 1 and 5 memories.

## Posts from {{DATE}}

{{POSTS}}

## Output Format
Return a JSON object with the following structure:
{{SCHEMA}}"""


class MemoryPromptBuilder:
    """Build one ``PromptItem`` per day from a flat list of threads."""

    def __init__(self, threads: list[Thread]) -> None:
        self.threads = [t for t in threads if t.asset_uri is not None]

    def build(self) -> list[PromptItem]:
        by_day: dict[date, list[Thread]] = defaultdict(list)
        for t in self.threads:
            by_day[t.asat.date()].append(t)

        schema_text = MemorySchema.format_schema_for_prompt()
        response_schema = MemorySchema.json_schema()

        items: list[PromptItem] = []
        for day, day_threads in sorted(by_day.items()):
            posts_block, asset_paths = self._format_posts(day_threads)
            prompt = (
                MEMORIES_PROMPT.replace("{{DATE}}", day.isoformat())
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
        threads: list[Thread],
    ) -> tuple[str, list[str]]:
        """Format thread previews and collect asset paths.

        Returns ``(text_block, asset_paths)`` where images in
        *asset_paths* are in the same order as ``[Image N]`` labels
        in *text_block*.
        """
        lines: list[str] = []
        asset_paths: list[str] = []
        img_idx = 0
        for t in threads:
            if t.asset_uri:
                img_idx += 1
                line = f"- [Image {img_idx}] {t.preview}"
                asset_paths.append(t.asset_uri)
            else:
                line = f"- {t.preview}"
            lines.append(line)
        return "\n".join(lines), asset_paths

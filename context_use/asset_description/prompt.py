from __future__ import annotations

import mimetypes

from pydantic import BaseModel, Field

from context_use.llm.base import PromptItem
from context_use.models.thread import Thread


def is_supported_media(uri: str, prefixes: tuple[str, ...]) -> bool:
    mime, _ = mimetypes.guess_type(uri)
    return mime is not None and any(mime.startswith(p) for p in prefixes)


ASSET_DESCRIPTION_PROMPT = """Describe this image or video focusing on:
- The main subject and activity
- Key visual elements that define the content
- Context and setting (location type, time of day if visible)
- Any notable people, objects, or brands that are clearly featured

Keep the description to a single sentence.
Focus on what makes this content meaningful to the person who captured it.
Avoid describing generic background elements.

If a caption is provided, use it to better understand the context.

## Caption
{{CAPTION}}

## Output Format
Return a JSON object with the following field:
{{SCHEMA}}"""


class AssetDescriptionSchema(BaseModel):
    description: str = Field(
        default="",
        description="A single sentence description of the image or video content",
    )

    @classmethod
    def json_schema(cls) -> dict:
        return cls.model_json_schema()

    @classmethod
    def format_schema_for_prompt(cls) -> str:
        schema = cls.model_json_schema()
        return "\n".join(
            f"- `{name}`: {prop.get('description', '')}"
            for name, prop in schema.get("properties", {}).items()
        )


class AssetDescriptionPromptBuilder:
    def __init__(self, threads: list[Thread]) -> None:
        self.threads = [t for t in threads if t.asset_uri is not None]

    def build(self) -> list[PromptItem]:
        response_schema = AssetDescriptionSchema.json_schema()
        prompt_template = ASSET_DESCRIPTION_PROMPT.replace(
            "{{SCHEMA}}", AssetDescriptionSchema.format_schema_for_prompt()
        )

        items: list[PromptItem] = []
        for thread in self.threads:
            caption = thread.get_raw_content() or "No caption provided"
            prompt = prompt_template.replace("{{CAPTION}}", caption)
            items.append(
                PromptItem(
                    item_id=thread.id,
                    prompt=prompt,
                    asset_uris=[thread.asset_uri],  # type: ignore[list-item]
                    response_schema=response_schema,
                )
            )
        return items

from __future__ import annotations

from pydantic import BaseModel, Field

from context_use.llm.base import PromptItem
from context_use.models.facet import Facet


class FacetDescriptionSchema(BaseModel):
    short_description: str = Field(
        description="One sentence summarising who or what this facet represents"
    )
    long_description: str = Field(
        description=(
            "A detailed, synthesised profile of this facet based on the provided "
            "memories. Focus on stable characteristics, preferences, patterns, and "
            "relationships — do not simply narrate or list the individual memories."
        )
    )

    @classmethod
    def json_schema(cls) -> dict:
        return cls.model_json_schema()


def build_facet_description_prompt(facet: Facet, memories: list[str]) -> PromptItem:
    memories_text = "\n".join(f"- {m}" for m in memories)
    prompt = (
        f"You are building a knowledge profile for a facet extracted from a user's "
        f"memories.\n\n"
        f"Facet type: {facet.facet_type}\n"
        f"Facet canonical value: {facet.facet_canonical}\n\n"
        f"## Memories\n\n"
        f"{memories_text}\n\n"
        f"## Instructions\n\n"
        f"Based solely on the memories above, produce two descriptions:\n\n"
        f"1. **short_description**: A single sentence identifying who or what "
        f'"{facet.facet_canonical}" is in the context of the user\'s life.\n\n'
        f"2. **long_description**: A detailed profile synthesising the stable "
        f"characteristics, preferences, recurring patterns, and relationships "
        f"evident across the memories. Do not list or narrate individual memories — "
        f"distil what is persistently true about this facet.\n\n"
        f"Return a JSON object with exactly two fields: "
        f"`short_description` and `long_description`."
    )
    return PromptItem(
        item_id=facet.id,
        prompt=prompt,
        response_schema=FacetDescriptionSchema.json_schema(),
    )

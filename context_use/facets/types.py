from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class FacetTypeDef:
    name: str
    description: str
    examples: list[str]
    exclude: str


FACET_TYPES: tuple[FacetTypeDef, ...] = (
    FacetTypeDef(
        name="person",
        description="A named individual mentioned by name or role.",
        examples=["Alice", "my manager John", "Dr. Smith"],
        exclude="Do not use for unnamed groups ('some colleagues', 'a few friends').",
    ),
    FacetTypeDef(
        name="location",
        description=(
            "A place: city, country, venue, neighbourhood, landmark, or address."
        ),
        examples=["London", "the Tate Modern", "Brooklyn", "Student Project House"],
        exclude=(
            "Do not use for vague references ('somewhere nearby', 'a coffee shop')."
        ),
    ),
    FacetTypeDef(
        name="organization",
        description=(
            "A named company, institution, team, or group the user interacts with."
        ),
        examples=["Stripe", "NHS", "GMG Seta", "University of Milan", "The Beatles"],
        exclude=(
            "Do not use for unnamed or generic entities "
            "('my employer', 'a startup', 'the design team')."
        ),
    ),
    FacetTypeDef(
        name="thing",
        description=(
            "A specific named thing: a tool, software, framework, device, book, film, "
            "album, brand, product, or any other proper-noun artifact."
        ),
        examples=[
            "React",
            "PostgreSQL",
            "iPhone 15",
            "The Great Gatsby",
            "Nikon Z8",
        ],
        exclude=(
            "Do not use for generic categories ('a database', 'some book', 'a phone'). "
            "Do not use for overly granular fragments "
            "('SQL SELECT statement', 'chapter 3', 'the login button')."
        ),
    ),
    FacetTypeDef(
        name="topic",
        description=(
            "A subject, theme, or area of interest that the memory is about, "
            "when it does not fit the other types."
        ),
        examples=["machine learning", "nutrition", "personal finance", "travel"],
        exclude=("Do not duplicate what is already captured by the other facet types."),
    ),
)

FacetType = Literal["person", "location", "organization", "thing", "topic"]

VALID_FACET_TYPES: frozenset[str] = frozenset(t.name for t in FACET_TYPES)


def render_facet_types_section() -> str:
    lines: list[str] = []
    for t in FACET_TYPES:
        examples = ", ".join(f'"{e}"' for e in t.examples)
        lines.append(
            f"- **{t.name}** — {t.description} Examples: {examples}. {t.exclude}"
        )
    return "### Facet types\n\n" + "\n".join(lines)

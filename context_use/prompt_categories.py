from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LifeCategory:
    """A dimension of a person's life that prompts should attend to."""

    name: str
    description: str


LIFE_CATEGORIES: tuple[LifeCategory, ...] = (
    LifeCategory(
        "Work and projects",
        "what they're building, debugging, designing, or deciding. "
        "Name specific technologies, frameworks, tools.",
    ),
    LifeCategory(
        "Decisions and preferences",
        "choices made, opinions expressed, trade-offs weighed. "
        "These reveal how the user thinks.",
    ),
    LifeCategory(
        "People and relationships",
        "anyone mentioned by name or role "
        "(partner, colleague, friend, family). Note the relationship "
        "and any context about that person.",
    ),
    LifeCategory(
        "Emotional state",
        "frustration, excitement, anxiety, pride, nostalgia, "
        "uncertainty, curiosity. How the user felt about what "
        "they were doing.",
    ),
    LifeCategory(
        "Life events",
        "moves, trips, job changes, celebrations, losses, health "
        "issues, milestones. These anchor who the user is in time.",
    ),
    LifeCategory(
        "Interests and hobbies",
        "books, music, cooking, fitness, travel, games, creative "
        "projects, fashion, art — anything beyond work.",
    ),
    LifeCategory(
        "Health and wellbeing",
        "exercise routines, dietary choices, sleep, medical concerns, mental health.",
    ),
    LifeCategory(
        "Values and beliefs",
        "positions taken, principles expressed, things they care "
        "about or push back on.",
    ),
    LifeCategory(
        "Goals and aspirations",
        "what the user wants to achieve, learn, change, or build.",
    ),
    LifeCategory(
        "Places and travel",
        "locations, cities, venues, landmarks, neighbourhoods.",
    ),
    LifeCategory(
        "Routines and habits",
        "recurring patterns that reveal daily life.",
    ),
    LifeCategory(
        "Personal context",
        "role, location, background, constraints, identity.",
    ),
)


_PROFILE_EXTRA_CATEGORIES: tuple[LifeCategory, ...] = (
    LifeCategory(
        "Personality and communication",
        "how they think, communicate, make decisions. "
        "Analytical or intuitive? Detail-oriented or big-picture?",
    ),
    LifeCategory(
        "Preferences and taste",
        "food, travel style, tools, aesthetic, brands, communication preferences.",
    ),
    LifeCategory(
        "Current life context",
        "what is happening in their life right now. "
        "Recent moves, transitions, projects, challenges.",
    ),
)


def _render_bullets(categories: tuple[LifeCategory, ...]) -> str:
    return "\n".join(f"- **{c.name}** — {c.description}" for c in categories)


WHAT_TO_CAPTURE: str = (
    "### What to capture\n"
    "\n"
    "Extract anything that reveals who this person is:\n"
    "\n" + _render_bullets(LIFE_CATEGORIES)
)

PROFILE_SECTIONS: str = (
    "### Suggested sections\n"
    "\n"
    "Organise the profile into sections that best fit the evidence. These are "
    "suggestions — add, remove, rename, or merge sections as the data "
    "warrants:\n"
    "\n" + _render_bullets(LIFE_CATEGORIES + _PROFILE_EXTRA_CATEGORIES)
)

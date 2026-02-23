from __future__ import annotations

from context_use.models.memory import TapestryMemory

PROFILE_PROMPT = """\
You are given a collection of first-person memories from a user's life. \
Each memory is a 1-3 sentence vivid recollection with a date range.

{{CURRENT_PROFILE_BLOCK}}\
## Your task

Produce a **user profile** in markdown that captures who this person \
truly is — their identity, how they spend their time, who matters to \
them, and what drives them. The profile should read like a rich, \
specific dossier that would let someone who has never met this person \
understand them deeply.

This profile will be used as context by an AI assistant interacting \
with this person. The more nuanced and accurate it is, the better the \
assistant can serve them.

### Suggested sections

Organise the profile into sections that best fit the evidence. These are \
suggestions — add, remove, rename, or merge sections as the data warrants:

- **Identity** — name, location, nationality, languages, age, \
background
- **Work & career** — role, company, industry, tools, current projects, \
career trajectory, professional interests
- **Relationships & social life** — key people by name and relationship \
(partner, family, friends, colleagues, pets). Who do they spend time \
with? Who do they mention often?
- **Personality & communication** — how they think, communicate, make \
decisions. Are they analytical or intuitive? Detail-oriented or \
big-picture? Patient or impatient?
- **Values & beliefs** — what they care about, principles they express, \
things they push back on or advocate for
- **Interests & hobbies** — what they do outside work. Be specific: \
not "likes music" but "plays jazz piano" or "listens to ambient \
electronic music"
- **Health & wellbeing** — exercise habits, dietary preferences, health \
concerns, sleep patterns, mental health awareness
- **Preferences & taste** — food, travel style, tools, aesthetic, \
brands, communication preferences
- **Current life context** — what is happening in their life right now. \
Recent moves, transitions, projects, challenges. This section should \
reflect the most recent memories and capture where they are in life \
today.

### Rules

- Only state facts supported by the memories. Do not fabricate.
- If an existing profile states something that no memory contradicts, \
preserve it.
- If new memories contradict the existing profile, update it — and note \
the change where relevant ("Previously at Company A, now at Company B \
since [date]").
- Write in third person ("They work at…" / use the person's name if \
known).
- Be specific: names, places, technologies, people — not vague \
summaries.
- Look for patterns across memories: recurring topics, people, places, \
or activities paint a richer picture than any single memory.
- Omit sections with no evidence rather than writing "Unknown".
- Do not include preamble, commentary, or meta-text — output only the \
markdown profile.

## Memories

{{MEMORIES}}
"""


def build_profile_prompt(
    memories: list[TapestryMemory],
    current_profile: str | None = None,
) -> str:
    """Assemble the full profile-generation prompt."""
    if current_profile:
        profile_block = f"## Current profile (update this)\n\n{current_profile}\n\n"
    else:
        profile_block = ""

    memory_lines: list[str] = []
    for m in sorted(memories, key=lambda m: m.from_date):
        date_range = (
            m.from_date.isoformat()
            if m.from_date == m.to_date
            else f"{m.from_date.isoformat()} to {m.to_date.isoformat()}"
        )
        memory_lines.append(f"- [{date_range}] {m.content}")

    memories_text = "\n".join(memory_lines) if memory_lines else "(no memories)"

    return PROFILE_PROMPT.replace("{{CURRENT_PROFILE_BLOCK}}", profile_block).replace(
        "{{MEMORIES}}", memories_text
    )

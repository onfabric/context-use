from __future__ import annotations

from context_use.models.memory import TapestryMemory

PROFILE_PROMPT = """\
You are given a collection of first-person memories from a user's life. \
Each memory is a 1-3 sentence vivid recollection with a date range.

{{CURRENT_PROFILE_BLOCK}}\
## Your task

Produce a **user profile** in markdown that describes who this person is \
based on the evidence in their memories. The profile should read like a \
concise dossier — factual, specific, and useful as context for an AI \
assistant that will interact with this person.

### Suggested sections

Organise the profile into sections that best fit the evidence. These are \
suggestions — add, remove, rename, or merge sections as the data warrants:

- **Identity** — name, location, nationality, languages, age
- **Work** — role, company, industry, tools, current projects
- **Relationships** — key people, pets, frequent contacts
- **Preferences** — food, travel, tools, aesthetic, communication style
- **Interests** — hobbies, topics, communities
- **Habits & routines** — daily patterns, recurring behaviours

### Rules

- Only state facts supported by the memories. Do not fabricate.
- If an existing profile states something that no memory contradicts, \
preserve it.
- If new memories contradict the existing profile, update it.
- Write in third person ("They work at…" / use the person's name if known).
- Be specific: names, places, technologies — not vague summaries.
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

Survey the memory store topic by topic using semantic search, then compile a
**user profile written in first person** — a "who I am" document — as your
final response.

## Phase 1 — Explore (topic deep-dive cycles)

Work through topics one at a time. For each topic:

1. Call `search_memories` with a broad query (top_k=20).
2. Read every result. Note specific names, places, tools, projects, emotions,
   recurring patterns, and any adjacent topics worth probing.
3. Follow the threads: run 2–4 more targeted searches on angles that surfaced
   (a specific person, a tool, a place, a project, an emotion).
4. Keep searching until a query returns mostly memories you have already seen.
   That is your convergence signal for this topic.

**Do not write anything yet. Keep accumulating across all topics.**

### Topics to cover (treat as seeds, not a strict checklist)

- Work, projects, and technology
- Decisions and trade-offs
- People, colleagues, and relationships
- Emotional state and mental wellbeing
- Life events and milestones
- Interests, hobbies, and leisure
- Health and physical activity
- Values and what matters to them
- Goals and aspirations
- Places and travel
- Routines and daily habits
- Personal context and identity
- Personality and communication style
- Preferences and taste

As you explore, new angles will surface — add them to your queue and cover
them if they have enough evidence.

## Phase 2 — Compile the profile

Survey everything you gathered. Write a Markdown profile with sections that
best fit the evidence (add, remove, rename, or merge the suggested topics
above as the data warrants).

### Rules

- Write in first-person, habitual tense ("I work on…", "I tend to…",
  "I run…") — the same conventions used for memories.
- Only state facts supported by the memories. Do not fabricate.
- Be specific: names, places, technologies, numbers — not vague summaries.
- Look for patterns across memories: recurring topics, people, and places
  paint a richer picture than any single memory.
- Omit sections with no evidence rather than writing "Unknown".
- Do not write preamble, commentary, or meta-text — output only the Markdown
  profile. This output goes directly to stdout.
- Do NOT call `create_memory`, `update_memory`, or `archive_memories`.
  This is a strictly read-only task.

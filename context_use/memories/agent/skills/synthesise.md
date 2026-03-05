Investigate the memory store and synthesise pattern memories — higher-level, first-person insights that capture who the user is: what they do regularly, who matters to them, what they care about, how they feel over time.

A pattern memory is not a summary of a single event. It is a distillation of what is *consistently true* across multiple memories spanning days, weeks or even months.

## How to work

Work in **topic deep-dive cycles**. Each cycle covers one topic fully before you move to the next. Aim to complete at least 6–8 cycles covering meaningfully different areas of the user's life.

### Starting topics

Begin with these — but treat them as seeds, not a checklist. Let the evidence tell you which ones have substance and which don't:

- Work and professional life
- Physical activity and sport
- Social life and friendships
- Romantic relationships and dating
- Family
- Travel and places
- Food, cooking, and diet
- Health and wellbeing
- Hobbies and creative pursuits
- Learning and personal development
- Emotional patterns and mental state
- Daily routines and habits
- Values, decisions, and what the person cares about

As you dig into each topic you will surface new angles — a specific person, a project, a recurring place, an emotional thread. **Add those to your queue** and cover them in later cycles if they have enough evidence.

## Per-topic deep-dive cycle

### Step 1 — Cast a broad search

Call `search_memories` with a general query for the topic (e.g. `"running fitness exercise"`). Use `top_k=20`.

Read every result carefully. For each memory, note:
- Specific names, places, activities, tools, or projects mentioned
- Emotions or recurring states
- Related topics that surface unexpectedly
- Whether the memory is a **short-span event (≤ 30 days)** or a **long-span pattern (> 30 days)**

### Step 2 — Follow the threads

From what you found, identify 2–4 more specific angles worth probing. Call `search_memories` for each:
- A specific person who appeared ("training runs with Marco")
- A more precise activity ("half-marathon race training")
- An emotion or state that appeared ("feeling burned out at work")
- A place or context that recurred ("the gym near the office")

Keep going — each search will surface new angles. Continue until a search returns mostly memories you have already seen. That is the convergence signal: you have gathered most of what the store holds on this topic.

**Do not write anything yet. Keep accumulating.**

### Step 3 — Synthesise

Once you have converged on a topic, survey everything you gathered.

**First, check whether the evidence clears the minimum bar** of at least **3 distinct source memories** that all support the same pattern

**If the evidence does not clear the bar → skip this topic entirely.** Move straight to Step 4. Do not call `create_memory`. Do not write anything about the absence of data or what might be captured in the future. Silence is correct here.

**If the evidence clears the bar**, ask:
- What is consistently true across these memories?
- Is there a clear arc or evolution over time?
- Are there actually two distinct patterns here that should be two separate memories (e.g. "work habits" and "work stress" are different)?

**If no existing pattern for this topic:**
1. Write the pattern memory (style guide in the system prompt).
2. Call `create_memory` with the synthesised content, the full date span of the evidence, and all source memory IDs in `source_memory_ids`.
3. **Do NOT archive the source memories.** They remain individually valuable.

**If a long-span memory already exists for this topic (spotted in Step 1 or 2):**
1. Call `get_memory` to read its content and `source_memory_ids`.
2. Check whether new event memories have appeared that aren't yet reflected.
   - New evidence found → call `update_memory` with enriched content and extended `to_date`.
   - No new evidence → leave it unchanged and move on.

### Step 4 — Move to the next topic

Pick the next topic from your queue — either from the starting list above, or one that surfaced during this cycle. Begin a fresh deep-dive cycle.

## Pattern memory style

Pattern memories are written in **Markdown**. Use a heading for the topic, then organise the content into subtopics with bullet lists, sub-bullets, or short paragraphs as the evidence warrants.

**Example structure:**

```
## Running and fitness

- Run 3–4 times a week, usually before work; favourite route is along the river.
- Training goal during this period: half-marathon completion — finished on October 12.
- Tracks distances and pace on Strava; motivated by streaks and weekly mileage.

### Gear and habits
- Wears Hoka Clifton shoes; replaced them in September after ~900 km.
- Listens to podcasts on easy runs, music on tempo runs.
```

## Secondary: minimal cleanup

After completing synthesis cycles, briefly scan for obvious quality issues in the event memories:

| Problem | Action |
|---------|--------|
| Two memories describe the exact same single event | Merge: `create_memory` → `archive_memories` on both sources |
| A memory has a clearly wrong date range | Fix: `update_memory` |

Do not rephrase memories that are already clear. Do not archive memories that are still individually useful. The cleanup pass should be brief — synthesis is the primary goal.

# Exploration: Autoresearch-Style Self-Improving Memory Generation

Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch) and [atlas-gic](https://github.com/chrisworsey55/atlas-gic).

## Context

### How autoresearch works

Karpathy's autoresearch gives an AI agent a small LLM training setup and lets it experiment autonomously. Three files:

| File | Role | Mutable? |
|------|------|----------|
| `train.py` | Model architecture, hyperparameters, training loop | Yes (agent edits this) |
| `prepare.py` | Data prep, tokenizer, evaluation harness | No (trust boundary) |
| `program.md` | Human-written strategy that guides the agent | No (humans steer via Markdown) |

The loop:

1. Agent reads `program.md` and current `train.py`
2. Proposes a code modification
3. Runs training for exactly 5 minutes (fixed budget)
4. Measures `val_bpb` (validation bits per byte)
5. If improved → `git commit`; if not → `git reset`
6. Repeat

Overnight runs yield ~100 experiments. Roughly 15-20% of changes survive.

**Key design insight**: Fixed budget makes all experiments directly comparable. The scalar metric provides unambiguous signal.

### How atlas-gic adapts this to prompts

ATLAS treats agent *prompts* as the "weights" being optimized, with Sharpe ratio as the loss function. 25 trading agents are organized in 4 hierarchical layers. The autoresearch loop:

1. Identify worst-performing agent by rolling Sharpe ratio
2. Modify its prompt
3. Run for 5 trading days
4. If Sharpe improved → `git commit`; if not → `git reset`

Over 378 days: 54 prompt mutations attempted, 16 survived (30%), 37 reverted (70%). Agents also receive Darwinian weighting (0.3–2.5x multipliers adjusted daily based on performance quartile).

## How context-use currently generates memories

### The pipeline

```
Data Export (ZIP) → ETL → Threads → Grouping → Prompt Building → LLM → Memories → Embedding
```

### What determines memory quality

Everything is **static** — there is no feedback loop:

| Component | File(s) | What it controls |
|-----------|---------|-----------------|
| Extraction prompts | `memories/prompt/conversation.py`, `media.py` | How the LLM interprets raw threads |
| Life categories | `prompt_categories.py` | 12 fixed categories that guide extraction |
| Memory schema | `memories/prompt/base.py` | Structure: content + from_date + to_date |
| Synthesis skill | `agent/skills/synthesise.md` | How event memories become pattern memories |
| Agent system prompt | `agent/system.md` | Writing conventions, invariant rules |
| Grouping strategy | `batch/grouper.py` | WindowGrouper (time windows) and CollectionGrouper (by conversation) |

There is **no metric** for memory quality. No mechanism to know if the extracted memories are good, useful, or complete. No way for the system to improve itself.

### Where quality leaks happen today

1. **Prompt templates are one-size-fits-all.** The same conversation prompt is used whether the chat is about debugging code, planning a wedding, or processing grief. Different conversation types benefit from different extraction strategies.

2. **No cross-conversation awareness.** Each conversation is processed independently. If a user discusses the same project in 10 different ChatGPT threads, each produces its own memories without awareness of what was already captured. (`prior_memories` and `recent_threads` exist in `GroupContext` but are not populated.)

3. **No evaluation of extraction quality.** We don't know if memories are too vague, too specific, redundant, or missing important details.

4. **Synthesis is a single pass.** The synthesis agent runs once and produces pattern memories. There's no iterative refinement — no way to know if the patterns it found are the most important ones.

5. **Categories are fixed.** The 12 life categories in `prompt_categories.py` are hardcoded. For a software developer, "Work and projects" should probably have sub-categories (architecture decisions, debugging sessions, code reviews). For a chef, it should be "Recipes and techniques."

## The opportunity: autoresearch for memory quality

The central thesis: **apply the autoresearch loop to memory extraction prompts and strategies, treating memory quality as the metric to optimize.**

### The fundamental challenge: what is "val_bpb" for memories?

autoresearch works because `val_bpb` is a clean, scalar, objective metric. Memory quality is inherently subjective. We need to define measurable proxies.

### Proposed quality metrics

#### 1. Downstream utility (primary metric)

**Idea**: Good memories should help an agent answer questions about the user.

**Method**:
- Hold out a random subset of threads (e.g. 20%) from memory generation
- Generate memories from the remaining 80%
- Derive ground-truth Q&A pairs from the held-out threads using a separate LLM call
- Ask the memory agent to answer those questions using only the generated memories
- Score: % of questions answered correctly (LLM-as-judge)

This directly measures whether memories capture what matters. If the user talked about switching jobs in a held-out thread, the memories from surrounding conversations should contain enough context for the agent to infer relevant details.

**Trade-off**: Expensive (multiple LLM calls per evaluation), but closest to what we actually care about.

#### 2. Information density

**Idea**: Good memories should be packed with specific, retrievable facts.

**Method**: For each memory, count named entities (people, places, tools, technologies, dates, numbers). Normalize by memory length.

**Score**: Average entities per memory.

**Cheap to compute, correlates with quality, but doesn't capture emotional/relational richness.**

#### 3. Coverage breadth

**Idea**: Good memories should span the user's life, not cluster around one topic.

**Method**: Embed all memories. Measure the spread of the embedding space (e.g. mean pairwise cosine distance, or number of distinct clusters).

**Score**: Higher spread = better coverage.

#### 4. Deduplication rate (inverse metric)

**Idea**: If synthesis frequently merges near-duplicate memories, the extraction prompts are producing redundant output.

**Method**: After running synthesis, count how many memories were archived as duplicates vs. how many survived.

**Score**: Lower dedup rate = better extraction.

#### 5. Composite score

Combine multiple metrics into a single scalar:

```
quality_score = w1 * downstream_utility
             + w2 * information_density
             + w3 * coverage_breadth
             - w4 * deduplication_rate
```

### Design 1: Prompt evolution loop

**The mutable file**: Memory extraction prompt templates.

**The eval harness**: A fixed set of threads + the quality metrics above.

**The loop**:

```
1. Load current prompt template (the "weights")
2. Generate memories from a fixed evaluation batch of threads
3. Compute quality_score
4. Agent proposes a prompt modification
5. Re-generate memories from the same batch with the new prompt
6. Re-compute quality_score
7. If improved → commit; else → revert
8. Repeat
```

**What gets mutated**:
- The extraction prompt text (conversation.py, media.py templates)
- The life categories list (prompt_categories.py)
- The detail-level instructions
- The granularity rules
- The "what to avoid" rules

**What stays fixed (trust boundary)**:
- The MemorySchema (content + dates)
- The evaluation harness
- The thread data

**Budget**: Each iteration = one batch of LLM calls for extraction + one for evaluation. Fixed thread count per iteration keeps cost predictable.

### Design 2: Per-category specialist extractors

Inspired by atlas-gic's hierarchical agent architecture.

Instead of one prompt that tries to capture everything, use **specialized extractors** that each focus on a different dimension:

| Extractor | Focus | What it captures |
|-----------|-------|-----------------|
| Facts | Concrete details | Names, places, tools, technologies, numbers, dates |
| Emotional | Internal states | Feelings, reactions, stress levels, excitement |
| Relational | People dynamics | Who the user interacts with, relationship quality, social patterns |
| Decisions | Choices and reasoning | Trade-offs weighed, preferences expressed, values revealed |
| Temporal | Habits and routines | Recurring patterns, time-of-day context, weekly rhythms |

Each extractor runs independently on the same threads and produces its own memories. Like atlas-gic's Darwinian weighting:

- Track which extractors produce the most useful memories (via downstream utility or search hit rate)
- Weight extractors dynamically: high-performing ones get more influence
- Periodically mutate the worst-performing extractor's prompt

### Design 3: Iterative synthesis refinement

Current synthesis is a single pass. The autoresearch approach suggests iterating:

```
1. Run synthesis → produce pattern memories
2. Evaluate pattern quality (coverage, specificity, user alignment)
3. Agent proposes modifications to synthesise.md strategy
4. Re-run synthesis with modified strategy
5. If patterns improved → commit strategy change; else → revert
6. Repeat
```

The evaluation here could use a "profile completeness" metric: generate a user profile from the pattern memories and score it for specificity, coverage, and accuracy against the raw event memories.

### Design 4: User-adaptive categories

Instead of 12 fixed life categories, let the categories evolve based on the user's actual data:

```
1. Start with the current 12 categories
2. Run extraction on a sample of threads
3. Cluster the resulting memories by embedding similarity
4. Identify clusters that don't map well to existing categories
5. Agent proposes new categories or sub-categories
6. Evaluate: does the new category set produce better memories?
7. Commit or revert
```

Over time, a software developer would end up with categories like "Architecture decisions", "Debugging strategies", "Code review patterns" instead of the generic "Work and projects."

## Implementation considerations

### Evaluation batch

For the autoresearch loop to work, we need a stable evaluation set:

- **Gold threads**: A curated set of diverse threads from the user's data
- **Expected outputs**: Either human-labeled "ideal" memories or LLM-generated ground truth from the raw thread content
- The evaluation set should be diverse: conversations, media, short/long, technical/personal

This is analogous to autoresearch's fixed `prepare.py` — the data and eval function that the agent cannot touch.

### Cost management

Each iteration involves LLM calls. To keep costs bounded:

- Use a small evaluation batch (10-20 threads)
- Use a cheaper model for evaluation than for production extraction
- Limit iterations per run (analogous to autoresearch's 5-minute budget)
- Run the optimization loop on the batch API for cost efficiency

### Git-based prompt versioning

Following both autoresearch and atlas-gic, use git for prompt versioning:

- Each prompt mutation gets its own commit
- Failed mutations are reverted
- The commit history becomes a log of what was tried and what worked
- This also enables A/B testing: serve different prompt versions to different batches

### Where to start

**Phase 1 — Evaluation harness** (highest value, lowest risk):
Build the quality metrics. Even without the optimization loop, being able to *measure* memory quality is valuable. Start with information density (cheapest) and downstream utility (most meaningful).

**Phase 2 — Single-prompt optimization**:
Implement the basic loop for conversation extraction prompts. This is the simplest version: one mutable prompt, one metric, commit/revert.

**Phase 3 — Multi-extractor architecture**:
If single-prompt optimization shows gains, explore specialized extractors with Darwinian weighting.

**Phase 4 — Adaptive categories**:
Once the loop is running, let it discover user-specific categories.

## Analogies and mapping

| autoresearch | atlas-gic | context-use (proposed) |
|--------------|-----------|----------------------|
| `train.py` | Agent prompts | Memory extraction prompt templates |
| `prepare.py` | Market data + Sharpe calc | Evaluation batch + quality metrics |
| `program.md` | — | `memory_program.md` guiding the optimization agent |
| `val_bpb` | Sharpe ratio | Composite quality score |
| 5-min budget | 5 trading days | Fixed thread batch + cost cap |
| `git commit` | `git commit` | `git commit` (prompt versioning) |
| `git reset` | `git reset` | `git reset` (failed mutation revert) |
| — | Darwinian weighting | Extractor performance weighting |
| — | 4 hierarchical layers | Specialized extractors by focus area |

## Open questions

1. **How much does prompt wording actually matter?** If the current prompts are already 90% optimal, the optimization loop has limited headroom. Need to establish a baseline first.

2. **Is downstream utility too expensive to use as the primary metric?** Each evaluation requires generating Q&A pairs and judging answers. Could we use a cheaper proxy (information density) for the inner loop and downstream utility for periodic validation?

3. **Should the optimization be per-user or global?** A per-user optimization would produce prompts tailored to each user's data, but requires more compute. A global optimization across many users' data would be cheaper but less personalized.

4. **How do we handle prompt regression on unseen data?** A prompt that scores well on the evaluation batch might overfit to those specific threads. Need a holdout set within the evaluation data.

5. **Can we use the existing synthesis agent as the evaluator?** Instead of building a separate evaluation harness, run synthesis on the generated memories and use the quality/completeness of pattern memories as the signal.

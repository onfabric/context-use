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

#### 6. Tiered evaluation architecture

Rather than choosing a single metric, use a pyramid where each tier gates the next. Cheap metrics run every iteration for fast signal; expensive metrics run periodically as a canary.

```
Tier 4 — Downstream utility Q&A        [every 10th iteration]
         (Q&A accuracy via LLM-as-judge)
Tier 3 — Synthesis probe                [every 5th iteration]
         (can patterns be formed?)
Tier 2 — Embedding coverage + dedup     [every iteration]
         (spread + redundancy)
Tier 1 — Structural validity + entities  [every iteration]
         (schema, dates, NER count)
```

**Tier 1 — Structural validity + entity density** (free/cheap): Verify memories conform to schema, dates are valid, content is non-empty. Count named entities (people, places, tools, dates, numbers) via spaCy NER or regex. Normalize by memory length. Zero LLM calls.

**Tier 2 — Embedding coverage + dedup rate** (cheap): Embeddings are already computed during memory creation. Measure spread (mean pairwise cosine distance or cluster count). Count near-duplicate pairs above a similarity threshold. Zero additional LLM calls.

**Tier 3 — Synthesis probe** (medium): Pick 3-4 diverse topics, retrieve relevant memories via vector search, ask an LLM to score evidence density, specificity, coherence, and coverage gaps. ~4 LLM calls per evaluation. See open question #5 for details.

**Tier 4 — Downstream utility** (expensive): Generate Q&A pairs from held-out threads, answer using only memories, judge correctness. ~40-60 LLM calls per evaluation. Run as a canary to ensure cheaper metrics correlate with real quality.

**Cost estimate for a 20-thread evaluation batch:**

| Tier | LLM calls | Run frequency | Role |
|------|-----------|---------------|------|
| 1 | 0 | Every iteration | Fast gate — reject obviously broken prompts |
| 2 | 0 | Every iteration | Inner-loop optimization signal |
| 3 | ~4 | Every 5th iteration | Richer quality signal |
| 4 | ~50 | Every 10th iteration | Ground-truth canary |

The composite score from metric #5 above uses Tiers 1-2 for the inner loop. If periodic canary checks (Tier 4) show the composite has diverged from real quality, recalibrate the weights.

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

#### Lighter alternative: conversation-type routing

Instead of running 5 parallel extractors, a cheaper approach is **classify-then-route**: classify each thread before extraction and route it to a specialized prompt variant.

1. Before extraction, classify each thread into a type: `technical`, `planning`, `emotional`, `informational`, `social`. This can be rule-based (presence of code blocks → technical, question-heavy with no code → informational) or a single cheap LLM call per thread.
2. Each type gets a variant of `_SHARED_BODY` that adjusts emphasis. For example, the `technical` variant de-emphasizes emotional state and emphasizes specific technologies, architecture decisions, and what the user learned. The `emotional` variant does the reverse.
3. The shared structure (granularity rules, output format, "what to avoid") stays identical across variants — only the "what to capture" emphasis shifts.

This achieves similar specialization to Design 2 at a fraction of the cost (1 extraction call per thread instead of 5), and is compatible with the optimization loop from Design 1 since each variant's prompt can be mutated independently.

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

### Structural prerequisites

Before building an optimization loop, two structural improvements should be made. Both are valuable independently and will raise the baseline that any future optimization loop operates on.

#### Populate GroupContext

`GroupContext` in `memories/prompt/base.py` already has `prior_memories` and `recent_threads` fields, and the prompt template in `_format_context` already renders them. But nothing populates them — they default to empty lists.

Wiring these up would give the extraction LLM cross-conversation awareness for free. When processing a batch, the memory manager could:

1. Query recently created memories for the same collection / time window.
2. Pass them as `prior_memories` so the LLM avoids re-extracting already-captured facts.
3. Pass trailing messages from the previous time window as `recent_threads` for continuity.

This directly addresses quality leak #2 (no cross-conversation awareness) without any ML or optimization loop. It is likely higher-ROI than prompt wording tweaks.

#### Headroom experiment

A one-time manual experiment to establish whether prompt optimization is worth the investment. See open question #1 for the full design: compare floor / baseline / ceiling extractions on 10-20 diverse threads. If the baseline is already within ~10% of the ceiling, the optimization loop has limited headroom and effort is better directed elsewhere.

### Where to start

**Phase 0 — Populate GroupContext** (structural fix, immediate quality gain):
Wire up `prior_memories` and `recent_threads` in the memory batch pipeline so the extraction LLM has cross-conversation awareness. No ML, no evaluation harness needed — just plumbing. Directly fixes quality leak #2.

**Phase 1 — Headroom experiment** (manual, gates further investment):
Run the floor/baseline/ceiling comparison on 10-20 diverse threads (see open question #1). If the gap between baseline and ceiling is small, skip Phases 3-4 and focus on structural improvements. If the gap is large, proceed.

**Phase 2 — Evaluation harness** (highest value, lowest risk):
Build the tiered metric stack (Tiers 1-3). Even without the optimization loop, being able to *measure* memory quality is valuable. Start with Tier 1+2 (entity density, embedding coverage, dedup rate) and add the synthesis probe (Tier 3). Downstream utility (Tier 4) can be added later as a canary.

**Phase 3 — Category adaptation** (per-user, highest-leverage optimization):
Implement Design 4: cluster a user's memory embeddings, compare to existing categories, propose refined categories. This is per-user optimization of the *lens*, not the technique. Likely produces more gains than prompt wording for users whose data is dominated by a few topics.

**Phase 4 — Prompt evolution loop** (global, only if headroom warrants it):
Implement Design 1: the full autoresearch loop for global extraction prompt optimization. Use k-fold evaluation with frozen holdout canary (see open question #4). Only pursue this if the headroom experiment in Phase 1 showed meaningful room for improvement.

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

## Proposed answers to open questions

### 1. How much does prompt wording actually matter?

**Approach**: Run a manual headroom experiment before building any automation.

Produce three extraction variants on the same 10-20 diverse threads:

| Variant | Prompt | Purpose |
|---------|--------|---------|
| Floor | Minimal instruction: "extract memories from this conversation as first-person journal entries" | Worst-case baseline |
| Baseline | Current production prompts | Status quo |
| Ceiling | Frontier model with chain-of-thought and full thread access, asked to write ideal memories | Best-case upper bound |

Compare the three on information density and a quick manual quality review. If baseline is already close to ceiling, prompt optimization has limited headroom and effort is better spent on structural improvements.

**Key observation**: `_SHARED_BODY` in `conversation.py` is shared across both `AgentConversationMemoryPromptBuilder` and `HumanConversationMemoryPromptBuilder`. Mutations affect both conversation types simultaneously. The headroom experiment should evaluate agent and human conversations separately to detect cases where one improves while the other regresses.

**Likely outcome**: Prompt wording matters moderately (15-30% improvement possible), but the highest-leverage change is probably populating `GroupContext.prior_memories` and `recent_threads` — fields that already exist in `memories/prompt/base.py` but are never filled. That is a structural fix, not an optimization-loop problem. See "Structural prerequisites" above.

### 2. Is downstream utility too expensive as the primary metric?

**Answer**: Yes, for the inner loop. Use a tiered "metric pyramid" instead.

Run cheap metrics every iteration for fast signal; run expensive metrics periodically as a canary to ensure the cheap proxies actually correlate with real quality. See "Tiered evaluation architecture" above for the full design.

The key insight is that downstream utility is the *validation* metric, not the *training* metric. Just as ML training uses batch loss for gradient steps and periodically checks held-out validation, the optimization loop uses cheap proxies (entity density, embedding coverage, dedup rate) for commit/revert decisions and periodically checks downstream utility to ensure the proxies haven't diverged from what we actually care about.

### 3. Should the optimization be per-user or global?

**Answer**: Split — global extraction prompts, per-user category adaptation.

The extraction prompts (`conversation.py`, `media.py`) encode *how to extract* — the technique of turning a conversation into memories. This is generalizable: a good extraction strategy works regardless of whether the conversation is about debugging Rust or planning a wedding. Global optimization benefits from diverse evaluation data across many users' threads.

The categories (`prompt_categories.py`) encode *what to look for* — the lens through which conversations are interpreted. This is where personalization matters. The current 12 `LIFE_CATEGORIES` are one-size-fits-all, and the doc identifies this as quality leak #5.

| Aspect | Scope | What mutates | Metric |
|--------|-------|-------------|--------|
| Extraction technique | Global | `_SHARED_BODY`, granularity rules, detail instructions | Composite of Tier 1+2 across diverse eval sets |
| Category adaptation | Per-user | `LIFE_CATEGORIES` tuple | Embedding coverage + entity density on that user's data |

### 4. How do we handle prompt regression on unseen data?

**Answer**: k-fold evaluation + a frozen holdout canary.

Structure the evaluation batch (e.g. 30 gold threads) as:

- **20 threads for k-fold optimization**: 5 folds of 4 threads each. Each iteration evaluates on one fold; rotate folds. A prompt mutation must improve on at least 3 of 5 folds to be committed. This prevents overfitting to a specific conversation style.
- **10 threads as a frozen holdout**: Never seen during the inner loop. Every 10th iteration, evaluate on the holdout. If holdout score drops more than a threshold below the fold scores, the prompt is overfitting — revert to the last canary-passing checkpoint.

The evaluation batch should be stratified for diversity:

- Mix of agent conversations and human conversations
- Mix of short (< 10 messages) and long (50+ messages) threads
- Mix of technical and personal content
- Mix of providers (ChatGPT, Claude, Instagram DMs, etc.)

### 5. Can we use the existing synthesis agent as the evaluator?

**Answer**: Yes, but as a "synthesis probe" — a stripped-down variant, not the full synthesis skill.

The full synthesis flow in `synthesise.md` runs 6-8 deep-dive cycles with multiple `search_memories` and `create_memory` calls. Too expensive for evaluation. But the *signal* from synthesis is valuable: can good patterns be formed from these memories?

The synthesis probe runs a single abbreviated cycle per topic:

1. Pick 3-4 diverse topics from the evaluation batch.
2. For each topic: embed a query and retrieve relevant memories via vector search (no agent loop).
3. Pass ~20 retrieved memories to an LLM in a single call and ask it to score:
   - **Evidence density**: how many memories support the topic?
   - **Specificity**: do memories contain named entities, dates, concrete details?
   - **Coherence**: do memories from the same topic form a consistent narrative?
   - **Coverage gaps**: are there obvious holes where you'd expect memories but find none?
4. Aggregate into a single "synthesis readiness" score.

Cost: ~4 LLM calls per evaluation (one per topic). Cheap enough for Tier 3 in the metric pyramid but more meaningful than purely statistical metrics.

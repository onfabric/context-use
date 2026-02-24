# Contributing to context-use

context-use has two main pipelines: **ETL** (extract + transform data from provider archives into normalised threads) and **Memories** (group threads, generate first-person memories via LLM, and embed them for semantic search). Both are configured in the unified provider registry.

---

## Quick Reference — Checklist

For a new pipe in an **existing** provider (e.g. adding messages to `instagram`):

| Step | File | Action |
|------|------|--------|
| 1 | `context_use/providers/<provider>/schemas.py` | Add Pydantic record model(s) |
| 2 | `context_use/providers/<provider>/<module>.py` | Create `Pipe` subclass with `extract()` + `transform()`, define `INTERACTION_CONFIG` |
| 3 | `context_use/providers/<provider>/__init__.py` | Add the new config to `PROVIDER_CONFIG.interactions` |
| 4 | `tests/fixtures/users/alice/<provider>/v1/...` | Add fixture data (real archive structure) |
| 5 | `tests/test_<provider>_<type>.py` | Subclass `PipeTestKit` + add provider-specific tests |

For a **new** provider, also:

| Step | File | Action |
|------|------|--------|
| A | `context_use/providers/<provider>/` | Create package (`__init__.py`, `schemas.py`, pipe module) |
| B | `context_use/providers/registry.py` | Add `Provider` enum member + import `PROVIDER_CONFIG` into `PROVIDER_REGISTRY` |

If the provider needs a new fibre (payload) type, see [Extending Payload Models](#extending-payload-models).

---

## Package Layout

```
context_use/
  models/                 ← domain models (pure dataclasses, no ORM)
  store/                  ← storage abstraction (pluggable backends)
  providers/              ← unified provider configs (ETL + memory)
  etl/                    ← reusable ETL building blocks
  memories/               ← reusable memory building blocks
  batch/                  ← reusable batch/grouping building blocks
  facade/                 ← public API
```

**Dependency rule:** All non-persistence code imports domain models from `context_use.models`, never from ORM models in `etl/models/`. The `store/` package bridges domain models to persistence. `providers` imports from `etl`, `memories`, and `batch`. Those three never import from `providers`.

---

## Architecture Overview

```
  ZIP archive
       │
       ▼
  ┌────────────────────────────────────────────────┐
  │  ETL Pipeline                                   │
  │                                                 │
  │  Pipe.extract()  →  Pipe.transform()  →  Store  │
  │  (parse archive)    (→ ThreadRow)    (persist)  │
  └────────────────────┬───────────────────────────┘
                       │
                  Thread rows in Store
                       │
                       ▼
  ┌────────────────────────────────────────────────┐
  │  Memory Pipeline                                │
  │                                                 │
  │  Grouper         →  PromptBuilder  →  LLM batch │
  │  (partition          (format           (generate │
  │   threads)            prompts)          memories)│
  │                                         │       │
  │                                         ▼       │
  │                                    Embed batch  │
  │                                    (vectorise)  │
  └────────────────────────────────────────────────┘
                       │
                  Memories + embeddings in Store
                       │
                       ▼
                  Semantic search
```

Key design rules:

- **Pipe is ET, not ETL.** Load is handled by the `Store`.
- **One Pipe class = one interaction type.** Each subclass handles one kind of data (e.g. stories, reels, DMs).
- **`Pipe.run()` yields `Iterator[ThreadRow]`.** Memory-bounded; the facade collects and persists via `Store.insert_threads()`.
- **`InteractionConfig` = pipe + memory config.** Declared once per interaction type, co-located with the pipe class.
- **Memory generation is async and batched.** The `MemoryBatchManager` state machine submits OpenAI batch jobs for both generation and embedding, polling until complete.
- **Store is pluggable.** `InMemoryStore` runs with zero external dependencies; `PostgresStore` adds persistence with pgvector for semantic search.

---

## Store Abstraction

All data access goes through the `Store` ABC — see `context_use/store/base.py` for the full interface with all abstract methods and docstrings.

| Store | Module | Use case |
|-------|--------|----------|
| `InMemoryStore` | `store/memory.py` | Default. No external deps. Data lives in Python dicts for the process lifetime. |
| `PostgresStore` | `store/postgres.py` | Persistent. Requires PostgreSQL + pgvector. |

All Store methods accept and return **domain models** from `context_use/models/` — pure Python dataclasses with no ORM dependencies.

---

## Unified Registry

Configuration flows through three layers — each provider owns its config while the framework stays clean:

| Layer | Key file | What to read |
|-------|----------|-------------|
| Shared types | `context_use/providers/types.py` | `InteractionConfig`, `ProviderConfig` dataclasses |
| Per-interaction | `context_use/providers/<provider>/<module>.py` | `INTERACTION_CONFIG` co-located with each pipe class |
| Per-provider | `context_use/providers/<provider>/__init__.py` | `PROVIDER_CONFIG` assembling the provider's interaction configs |
| Global registry | `context_use/providers/registry.py` | `Provider` enum, `PROVIDER_REGISTRY` dict |

Each provider subdirectory under `context_use/providers/` shows how `INTERACTION_CONFIG` is co-located with its pipe class and assembled into `PROVIDER_CONFIG` in the package `__init__.py`. Browse the existing providers to see the pattern.

### Adding a pipe to an existing provider

1. In the pipe module, define `INTERACTION_CONFIG` with the pipe class and its `MemoryConfig` (set `memory=None` for ETL-only interaction types).
2. In the provider's `__init__.py`, import it and add it to the `PROVIDER_CONFIG.interactions` list.

No changes to `registry.py` needed.

### Adding a new provider

1. Create the provider package under `context_use/providers/<provider>/` with `schemas.py`, pipe module(s), and `__init__.py` assembling `PROVIDER_CONFIG`.
2. Add a member to the `Provider` enum in `context_use/providers/registry.py`.
3. Import and add the provider config to `PROVIDER_REGISTRY` in the same file.

---

## ETL Pipe Reference

### Writing a Pipe

The base class is `context_use/etl/core/pipe.py` — read it; it's ~90 lines with full docstrings on every ClassVar and method. The output type is `ThreadRow` in `context_use/etl/core/types.py`.

See `context_use/providers/` for working implementations — each provider subdirectory contains complete pipes. Different providers have different extraction logic (e.g. streaming large JSON with `ijson`, parsing manifests, fan-out with one file per conversation). When writing a new pipe, browse the existing providers to find the closest pattern.

#### Required ClassVars

Every `Pipe` subclass must set: `provider`, `interaction_type`, `archive_version`, `archive_path_pattern`, `record_schema`. See the base class docstrings for details.

#### `extract()` Contract

- Read from `storage.read(task.source_uri)` (small files) or `storage.open_stream(task.source_uri)` (large files — streaming with `ijson`).
- Yield one validated Pydantic model per logical item.
- Filter bad/irrelevant records here — don't push that into `transform()`.

#### `transform()` Contract

- Build an ActivityStreams payload using Fibre models from `context_use/etl/payload/models.py`.
- Return a `ThreadRow` with all required fields (see `context_use/etl/core/types.py`).
- Set `unique_key` as `f"{self.interaction_type}:{payload.unique_key_suffix()}"`.
- Set `preview` via `payload.get_preview(provider)`.
- For media pipes, set `asset_uri` as `f"{task.archive_id}/{record.uri}"`.

#### `run()` — Do Not Override

`run()` is a template method on the base class. It calls `extract()`, then `transform()` for each record, and yields `ThreadRow` instances lazily.

### Record Schemas

Record schemas are Pydantic `BaseModel` subclasses that `extract()` yields. Rules:

- Include a `source: str | None = None` field so `transform()` can stash the raw JSON for audit/debug.
- Name descriptively — the class name appears in test output.

See existing schemas in each provider's `schemas.py`.

### Glob Patterns (`archive_path_pattern`)

Uses Python's `fnmatch` syntax relative to the archive root (not including the archive ID prefix). Patterns without wildcards match exactly one file. Patterns with wildcards create **one EtlTask per matched file** (fan-out). See `ProviderConfig.discover_tasks()` in `context_use/providers/types.py`.

### Extending Payload Models

Payload models live in `context_use/etl/payload/models.py`. They follow ActivityStreams 2.0 conventions.

**Before creating a new fibre type**, check the existing ones in that file — most new pipes will use `FibreSendMessage`, `FibreReceiveMessage`, or `FibreCreateObject`.

To add a new fibre type:

1. Subclass the appropriate AS base (`Activity` or `Object`) with `_BaseFibreMixin`
2. Add a `fibreKind` literal field
3. Implement `_get_preview()`
4. Call `model_rebuild()` at module level
5. Add to the `FibreByType` discriminated union at the bottom of the file

The mixin provides: `unique_key_suffix()`, `to_dict()`, `get_preview()`, `get_asat()`. See how existing pipes in `context_use/providers/` build payloads in their `transform()` methods.

### Shared Base Class Pattern

When a provider has multiple interaction types that share the same `record_schema` and `transform()` logic, extract the shared code into a private base class. Only the concrete subclasses (which set `interaction_type` and `archive_path_pattern`) get registered. See the Instagram media pipes in `context_use/providers/instagram/media.py` for this pattern.

### Versioning via Inheritance

If a provider ships a new archive format, **don't edit the existing pipe**. Subclass it, override `extract()`, and set a new `archive_version` / `archive_path_pattern`. `transform()` is inherited when the `record_schema` stays the same.

`archive_version` tracks the **provider's export format**; `ThreadRow.version` tracks the **payload schema** version (`CURRENT_THREAD_PAYLOAD_VERSION`). They are independent.

### Storage

Pipes interact with storage via the `StorageBackend` ABC (`context_use/storage/base.py`):

- `storage.read(key) -> bytes` — read a file in full (good for small JSON files).
- `storage.open_stream(key) -> BinaryIO` — open a stream (good for large files).

The `key` is the full path including the archive ID prefix, e.g. `archive/conversations.json`.

---

## Memory Pipeline

### How It Works

1. **Group threads** — `ThreadGrouper` partitions threads into groups, each becoming one LLM prompt.
2. **Build prompts** — `BasePromptBuilder` formats each group into a `PromptItem`.
3. **Submit to LLM** — `MemoryExtractor` sends an OpenAI batch job. The LLM returns `MemorySchema` responses.
4. **Store memories** — parsed memories are persisted.
5. **Embed memories** — a second batch job vectorises each memory for semantic search.

### MemoryBatchManager State Machine

See `context_use/memories/manager.py`. States: `CREATED → MEMORY_GENERATE_PENDING → MEMORY_GENERATE_COMPLETE → MEMORY_EMBED_PENDING → MEMORY_EMBED_COMPLETE → COMPLETE`. At any point → `SKIPPED` (no content) or `FAILED` (error).

### MemoryConfig

See `context_use/memories/config.py` — declares `prompt_builder`, `grouper`, and optional kwargs for each. Factory methods: `create_prompt_builder(contexts)` and `create_grouper()`.

### Groupers

See `context_use/batch/grouper.py` for the ABC and both stock implementations.

| Grouper | Group key | Use case |
|---------|-----------|----------|
| `WindowGrouper` | Time window | Sliding time-window; good for media (stories, reels) |
| `CollectionGrouper` | Collection ID from payload | Group by conversation / thread ID; good for chats |

To write a custom grouper, subclass `ThreadGrouper` and implement `group(threads) -> list[ThreadGroup]`.

### Prompt Builders

See `context_use/memories/prompt/base.py` for the ABC (`BasePromptBuilder`) and `GroupContext` / `MemorySchema` models.

| Builder | Module | Use case |
|---------|--------|----------|
| `ConversationMemoryPromptBuilder` | `memories/prompt/conversation.py` | Chat / DM transcripts |
| `MediaMemoryPromptBuilder` | `memories/prompt/media.py` | Visual media grouped by day |

To write a custom prompt builder, subclass `BasePromptBuilder` (or a stock builder) and implement `build()` and `has_content()`.

### Reusable combinations

| Interaction pattern | Grouper | Prompt builder |
|---------------------|---------|----------------|
| Chat / DM conversations | `CollectionGrouper` | `ConversationMemoryPromptBuilder` |
| Visual media (stories, reels, posts) | `WindowGrouper` | `MediaMemoryPromptBuilder` |

---

## Testing

### PipeTestKit

See `context_use/testing/pipe_test_kit.py` — it's ~160 lines and fully docstringed. Subclass it and provide:

- `pipe_class` — the `Pipe` subclass under test
- `expected_extract_count` / `expected_transform_count` — expected counts from the fixture
- `pipe_fixture` — pytest fixture returning `(StorageBackend, key)`

The kit auto-generates: extract type/count checks, ThreadRow structural validation (including `unique_key` prefix, `fibreKind` in payload, non-empty preview), unique key checks, count tracking, and ClassVar validation. Read the class for the full list.

See `tests/unit/etl/` for working test suites — each test file demonstrates `PipeTestKit` subclassing alongside provider-specific assertions (message direction, asset URIs, edge-case filtering, payload structure).

### Fixture Data

Place realistic test data under `tests/fixtures/users/alice/<provider>/<archive_version>/`, mirroring the actual archive directory structure. The fixture JSON should exercise edge cases while staying small enough to reason about.

### Storage in Tests

Use `DiskStorage(str(tmp_path / "store"))` backed by pytest's `tmp_path`. Write fixture data with `storage.write(key, data)`.

Use `self._make_task(key)` to build a transient `EtlTask` in provider-specific tests.

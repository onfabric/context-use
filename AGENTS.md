# Contributing to context-use

context-use has two main pipelines: **ETL** (extract + transform data from provider archives into normalised threads) and **Memories** (group threads, generate first-person memories via LLM, and embed them for semantic search). Both are configured in the unified provider registry.

---

## Development setup

```bash
git clone https://github.com/onfabric/context-use.git
cd context-use
uv sync
uv run pre-commit install
```

`uv sync` installs all dependencies including dev and all optional extras (`postgres`, `gcs`, `mcp-use`, `adk`).

Run tests:

```bash
./scripts/prepare-tests.sh   # start test infrastructure (PostgreSQL)
./scripts/run-tests.sh
./scripts/shutdown-tests.sh
```

Type checking and linting:

```bash
uv run pyright
uv run ruff check --fix
uv run ruff format
```

---

## Quick Reference — Checklist

For a new pipe in an **existing** provider (e.g. adding messages to `instagram`):

| Step | File | Action |
|------|------|--------|
| 1 | `context_use/providers/<provider>/schemas.py` | Add Pydantic record model(s) |
| 2 | `context_use/providers/<provider>/<module>.py` | Create `Pipe` subclass with `extract_file()` + `transform()`, call `declare_interaction()` at module level |
| 3 | `context_use/providers/<provider>/__init__.py` | Import the new module (one line) so the registration fires |
| 4 | `tests/fixtures/users/alice/<provider>/v1/...` | Add fixture data (real archive structure) |
| 5 | `tests/unit/etl/test_<provider>_<type>.py` | Subclass `PipeTestKit` + add provider-specific tests |

For a **new** provider, also:

| Step | File | Action |
|------|------|--------|
| A | `context_use/providers/<provider>/` | Create package (`__init__.py`, `schemas.py`, pipe module(s)) |
| B | `context_use/providers/__init__.py` | Import the new provider package (one line) so it registers |

No changes to `registry.py` are ever needed.

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

Providers register themselves via two functions in `context_use/providers/registry.py`.  No edits to `registry.py` are ever needed when adding a new provider or interaction type.

| Layer | Key file | What to read |
|-------|----------|-------------|
| Shared types | `context_use/providers/types.py` | `InteractionConfig`, `ProviderConfig` dataclasses |
| Per-interaction | `context_use/providers/<provider>/<module>.py` | bare `declare_interaction()` calls at module level |
| Per-provider | `context_use/providers/<provider>/__init__.py` | module imports + `register_provider()` call |
| Top-level trigger | `context_use/providers/__init__.py` | imports each provider package to fire registration |

### `declare_interaction(config)`

Call this at module level in a pipe module.  It reads the provider name from `config.pipe.provider` (the ClassVar already on every `Pipe` subclass) and accumulates the config into an internal list.  Returns `None` — do not assign the result.

```python
# providers/instagram/media.py
from context_use.providers.instagram.schemas import PROVIDER
from context_use.providers.registry import declare_interaction

declare_interaction(InteractionConfig(pipe=InstagramStoriesPipe, memory=_MEDIA_MEMORY_CONFIG))
declare_interaction(InteractionConfig(pipe=InstagramReelsPipe, memory=_MEDIA_MEMORY_CONFIG))
```

### `register_provider(name, modules)`

Call this once in a provider `__init__.py`.  Pass every pipe module as `modules` — because module objects must be imported before they can be passed, this makes the dependency on those imports structurally explicit rather than relying on side-effect ordering.  Raises `ValueError` if any module in `modules` declared no interactions.  Returns `None` — do not assign the result.

```python
# providers/instagram/__init__.py
from context_use.providers.instagram import comments, connections, likes, media, ...
from context_use.providers.instagram.schemas import PROVIDER
from context_use.providers.registry import register_provider

register_provider(PROVIDER, modules=[comments, connections, likes, media, ...])
```

### Adding a pipe to an existing provider

1. In the pipe module, call `declare_interaction(InteractionConfig(...))` at module level for each pipe class.
2. In the provider's `__init__.py`, add one import line for the new module — this is what fires the declaration.

### Adding a new provider

1. Define `PROVIDER = "<name>"` in `schemas.py`. Import it into every pipe module (for the `provider` ClassVar) and into `__init__.py` (for `register_provider`). This is the single source of truth for the provider name.
2. Create the provider package under `context_use/providers/<provider>/` with `schemas.py`, pipe module(s), and `__init__.py` that imports the submodules and calls `register_provider(PROVIDER, modules=[...])`.
3. Add one import line for the new provider package in `context_use/providers/__init__.py`.

---

## ETL Pipe Reference

### Writing a Pipe

The base class is `context_use/etl/core/pipe.py` — read it; it's ~90 lines with full docstrings on every ClassVar and method. The output type is `ThreadRow` in `context_use/etl/core/types.py`.

See `context_use/providers/` for working implementations — each provider subdirectory contains complete pipes. Different providers have different extraction logic (e.g. streaming large JSON with `ijson`, parsing manifests, fan-out with one file per conversation). When writing a new pipe, browse the existing providers to find the closest pattern.

#### Required ClassVars

Every `Pipe` subclass must set: `provider`, `interaction_type`, `archive_version`, `archive_path_pattern`, `record_schema`. See the base class docstrings for details.

#### `extract_file()` Contract

- Subclasses implement `extract_file(source_uri, storage)` — single-file logic only. The base class `extract()` loops over `task.source_uris` and delegates to `extract_file()` for each file.
- Read from `storage.read(source_uri)` (small files) or `storage.open_stream(source_uri)` (large files — streaming with `ijson`).
- Yield one validated Pydantic model per logical item.
- Filter bad/irrelevant records here — don't push that into `transform()`.

#### `transform()` Contract

- Build an ActivityStreams payload using Fibre models from `context_use/etl/payload/models.py`.
- Return a `ThreadRow` with all required fields (see `context_use/etl/core/types.py`).
- Set `unique_key` via `payload.unique_key()` (returns a content hash).
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

Uses Python's `fnmatch` syntax relative to the archive root (not including the archive ID prefix). Patterns without wildcards match exactly one file. Patterns with wildcards bundle **all matched files into one EtlTask** via `source_uris` (sorted for determinism). The base class `extract()` loops over `source_uris` and calls `extract_file()` for each, so subclasses always implement single-file logic. See `ProviderConfig.discover_tasks()` in `context_use/providers/types.py`.

### Extending Payload Models

Payload models live in `context_use/etl/payload/models.py`. They follow ActivityStreams 2.0 conventions.

**Before creating a new fibre type**, check the existing ones in that file — most new pipes will use `FibreSendMessage`, `FibreReceiveMessage`, or `FibreCreateObject`.

To add a new fibre type:

1. Subclass the appropriate AS base (`Activity` or `Object`) with `_BaseFibreMixin`
2. Add a `fibreKind` literal field
3. Implement `_get_preview()`
4. Call `model_rebuild()` at module level
5. Add to the `FibreByType` discriminated union at the bottom of the file

The mixin provides: `unique_key()`, `to_dict()`, `get_preview()`, `get_asat()`. See how existing pipes in `context_use/providers/` build payloads in their `transform()` methods.

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

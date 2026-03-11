# Adding a Data Provider

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

Key design rules:

- **Pipe is ET, not ETL.** Load is handled by the `Store`.
- **One Pipe class = one interaction type.** Each subclass handles one kind of data (e.g. stories, reels, DMs).
- **`Pipe.run()` yields `Iterator[ThreadRow]`.** Memory-bounded; the facade collects and persists via `Store.insert_threads()`.
- **`InteractionConfig` = pipe + memory config.** Declared once per interaction type, co-located with the pipe class.

---

### Steps and their purpose

The pipeline has two stages connected by a **record schema** — a Pydantic model you define per pipe.

**`extract_file(source_uri, storage) → Iterator[RecordSchema]`** answers: *what is in this file?*

- Parse the raw archive, flatten nested structures, and enrich each item with any file-level context.
- Yield one record per logical item — one message, one post, one comment.
- Capture **every field that could plausibly be useful** in `transform`: sender, recipients, timestamps, content text, media URIs, reaction counts, reply context, etc. When in doubt, include it.
- Keep field values as close to the source as possible. Do not compose strings, derive values, or make semantic decisions here.
- Skip only when data is **structurally unusable**: a required field is missing, or there is no renderable content at all.

**`transform(record, task) → ThreadRow`** answers: *what does this record mean?*

- Map the record's fields onto the appropriate fibre model. **Use all the information the record carries** — do not silently drop fields that have a place in the payload.
- Apply semantic logic where needed: detect system-generated strings, compose the human-readable content field, choose the right fibre type for variation within the pipe.
- **Do not introduce fields that have no basis in the record.** If a fibre field cannot be populated from the record, leave it unset rather than guessing.
- Build the fibre payload (see below) and return a `ThreadRow`.

### The record schema as interface

The record schema is a **contract between `extract_file` and `transform`** — a complete, faithful structured mirror of the useful raw data for one logical item.

- Include **every source field that could inform the transformation**: content, participants, media references, timestamps, context flags. Omit only fields that are provably irrelevant to any downstream use.
- Include a `source: str | None = None` field so `transform` can stash the raw JSON for audit.
- Keep field values as they appear in the source. Do not pre-compose strings or derive values — that is `transform`'s responsibility.

### Using payload (fibre) models

Fibre models in `context_use/etl/payload/models.py` are the shared vocabulary of what happened. Most pipes will use one of these:

| Fibre | When to use |
|---|---|
| `FibreSendMessage` | User sent a message to someone |
| `FibreReceiveMessage` | User received a message from someone |
| `FibreCreateObject` | User posted an image or video |
| `FibreViewObject` | User viewed a post, video, or reel |
| `FibreAddObject` | User added something to a collection (liked, saved) |
| `FibreFollowActor` / `FibreFollowedByActor` | Follow/follower events |
| `FibreCommentObject` | User commented on something |

ActivityStreams models use JSON-LD field aliases (`@type`, `@id`) that conflict with keyword construction. Build a plain dict and unpack it:

```python
ctx_kwargs: dict = {
    "type": "Collection",
    "id": f"https://example.com/{record.thread_id}",
    "name": record.title,
}
context = Collection(**ctx_kwargs)
```

Most AS model constructors also require a `# type: ignore[reportCallIssue]` suppression due to the alias mismatch with pyright.

**Do not add a new fibre type to accommodate small differences between records from the same pipe.** Variation within a pipe — a plain text message, a story reply, a shared post — is handled in `transform()` through content composition, not by creating new types. Fibre types represent categorically different kinds of interaction. If you think you need a new type, first check whether an existing one covers the semantic meaning; explain your reasoning in the PR.

To add a genuinely new fibre type: subclass the appropriate AS base (`Activity` or `Object`) with `_BaseFibreMixin`, add a `fibreKind` literal field, implement `_get_preview()`, call `model_rebuild()` at module level, and add it to the `FibreByType` union at the bottom of the file. The models have to be compliant with [Activity Streams 2.0](https://www.w3.org/TR/activitystreams-core/)

### Writing previews

`payload.get_preview(provider)` returns a short natural-language string stored in `ThreadRow.preview`. It is the primary input the memory pipeline feeds to the LLM — if the preview is weak, the generated memories will be weak.

A good preview reads like a sentence a person would say:

> "Sent message 'hey, when are you free?' to Alice on Instagram"
> "Received message 'sounds good, see you then' from Bob on Instagram"
> "Posted video on Instagram"

Rules for `_get_preview`:

- **Build the preview exclusively from the fibre payload fields** — never from the record, the raw source, or any external state. The payload is the only input available at preview time.
- Write a complete, human-readable sentence — not a label or metadata string.
- Include the provider name.
- Include actor/target names when known.
- For message content, truncate at ~100 characters with `...`.
- Omit technical identifiers: no IDs, URLs, or timestamps.

If the payload fields are too sparse to produce a meaningful sentence, that is a signal that `transform` is not populating the fibre model fully enough — fix the transformation, not the preview.

### Glob patterns (`archive_path_pattern`)

Uses `fnmatch` syntax relative to the archive root (no archive ID prefix). Patterns with wildcards bundle all matched files into one `EtlTask` via `source_uris` (sorted for determinism). `extract_file` always handles a single file — the base class loops.

### Storage

- `storage.read(key) → bytes` — read a file in full (small JSON files).
- `storage.open_stream(key) → BinaryIO` — open a stream (large files, use with `ijson`).

### Shared base class pattern

When a provider has multiple interaction types sharing the same `record_schema` and `transform()`, extract shared logic into a private base class. Only concrete subclasses (which set `interaction_type` and `archive_path_pattern`) get registered. See `context_use/providers/instagram/media.py`.

### Versioning via inheritance

To support a new archive format, subclass the existing pipe, override `extract_file()`, and set a new `archive_version` / `archive_path_pattern`. `transform()` is inherited when `record_schema` is unchanged.

`archive_version` tracks the provider's export format. `ThreadRow.version` tracks the payload schema version (`CURRENT_THREAD_PAYLOAD_VERSION`). They are independent.

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
| `AgentConversationMemoryPromptBuilder` | `memories/prompt/conversation.py` | Conversations with an AI assistant (ChatGPT, Claude) |
| `HumanConversationMemoryPromptBuilder` | `memories/prompt/conversation.py` | Conversations between people (DMs, chats) |
| `MediaMemoryPromptBuilder` | `memories/prompt/media.py` | Visual media grouped by day |

To write a custom prompt builder, subclass `BasePromptBuilder` (or a stock builder) and implement `build()` and `has_content()`.

### Reusable combinations

| Interaction pattern | Grouper | Prompt builder |
|---------------------|---------|----------------|
| AI assistant conversations | `CollectionGrouper` | `AgentConversationMemoryPromptBuilder` |
| Human-to-human conversations | `CollectionGrouper` | `HumanConversationMemoryPromptBuilder` |
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

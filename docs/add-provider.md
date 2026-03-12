# Adding a Data Provider

## Quick Reference — Checklist

For a new pipe in an **existing** provider (e.g. adding messages to `instagram`):

| Step | File | Action |
|------|------|--------|
| 1 | `context_use/providers/<provider>/schemas.py` | Add file schema(s) and record model(s) |
| 2 | `context_use/providers/<provider>/<module>.py` | Create `Pipe` subclass with `extract_file()` + `transform()`, call `declare_interaction()` at module level |
| 3 | `context_use/providers/<provider>/__init__.py` | Import the new module (one line) so the registration fires |
| 4 | `tests/fixtures/users/alice/<provider>/v1/...` | Add fixture data (real archive structure) |
| 5 | `tests/unit/etl/<provider>/test_<type>.py` | Subclass `PipeTestKit` (set `fixture_data`, `fixture_key`, counts) + add provider-specific tests |

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

- **Validate first.** Parse the raw file against its [file schema](#file-schemas). This is a breaking-change gate: if the file's structure no longer matches what the pipe expects, validation raises, and `extract()` logs a warning and skips the file. No transformation will run against a file that fails this check.
- Flatten the validated file's items into records, enriching each with any file-level context (e.g. fields that live at the file root rather than on each individual item).
- Yield one record per logical item — one message, one post, one comment.
- Capture **every field that could plausibly be useful** in `transform`: sender, recipients, timestamps, content text, media URIs, reaction counts, reply context, etc. When in doubt, include it.
- Keep field values as close to the source as possible. Do not compose strings, derive values, or make semantic decisions here.
- Skip only when data is **structurally unusable**: a required field is missing, or there is no renderable content at all.
- Extract filter criteria (role names, content types, etc.) to named module-level constants when they appear in more than one place. Single-use, self-evident values can stay as literals.
- When filtering requires checking multiple conditions, extract a dedicated predicate so the extract loop stays readable. Separate *what records we want* from *whether the record has usable content*; keep data-quality checks inline.

**`transform(record, task) → ThreadRow`** answers: *what does this record mean?*

- Map the record's fields onto the appropriate fibre model. **Use all the information the record carries** — do not silently drop fields that have a place in the payload.
- Apply semantic logic where needed: detect system-generated strings, compose the human-readable content field, choose the right fibre type for variation within the pipe.
- **Do not introduce fields that have no basis in the record.** If a fibre field cannot be populated from the record, leave it unset rather than guessing.
- When building a `Collection` context (e.g. for conversations or threads), set its `id` to the **real, user-facing URL** of the conversation or collection whenever possible. If the archive does not expose the public identifier, construct a stable synthetic URL from the data that is available and **add a comment** explaining that the URL is synthetic and why.
- Build the fibre payload (see below) and return a `ThreadRow`.

### File schemas

Each pipe validates its input via Pydantic models in `schemas.py`. How that validation is structured depends on the file's top-level structure.

**Files that are not a flat JSON array at the root** (an object with envelope fields, a nested structure, etc.) must be read in full with `storage.read()` and validated with a file-level schema. Its role is a breaking-change gate — if the file's structure no longer matches what the pipe expects, validation raises before any records are processed.

- If the file is a JSON object wrapping a list, model the object as a Pydantic class and make the list field a `list[ItemModel]` — not `list[dict]`.
- For each item model, declare every field the pipe reads as a typed attribute. Fields that are optional in the real data should be typed `field: T | None = None`. Required fields should have no default.
- Nested structures (sub-objects, inner arrays) must be modelled as Pydantic classes too — not left as `dict` or `dict[str, Any]`.
- Do not use `TypeAdapter(list[...])` — it loads the entire file into memory and is superseded by streaming for flat arrays and by a typed wrapper class for envelope objects.

**Files that are a flat JSON array at the root** must be streamed with `storage.open_stream()` + `ijson`. There is no whole-file schema in this case — define only the item model and validate each item individually as it is streamed (`ItemModel.model_validate(raw_item)` inside the loop). The item model is the validation gate: if an item fails, that item fails, not the entire file.

The only exception is genuinely opaque sub-structures — nested dicts whose internal schema is fully unknown and that the pipe never inspects. Use `dict[str, object] | None`, not `dict[str, Any] | None`; avoid `Any` wherever a concrete type is possible. When a field can hold values of different types (e.g. text parts and attachment parts in the same list), model it as a typed union rather than collapsing to the common base type.

**Do not suppress validation errors.** If a node or item fails validation, the schema does not accurately model the data — fix the schema. Silently swallowing errors (e.g. via `field_validator` try/except that returns `None`) hides schema drift and makes it impossible to detect when the provider changes its format.

**Allow extra fields** (Pydantic's default behaviour). Providers add fields over time; schemas must not reject files that contain fields beyond what the pipe currently uses. Only the removal or renaming of a field the pipe depends on should cause a validation failure.

In practice, follow the Instagram provider as a reference implementation: see `InstagramV1ActivityItem`, `InstagramCommentStringMapData`, `InstagramSavedPostSMD`, and related models in `context_use/providers/instagram/schemas.py`.

### The record schema as interface

The record schema is a **contract between `extract_file` and `transform`** — a complete, faithful, flat mirror of the useful raw data for one logical item.

- Include **every source field that could inform the transformation**: content, participants, media references, timestamps, context flags. Omit only fields that are provably irrelevant to any downstream use.
- Include a `source: str | None = None` field that holds the raw source item — as close to the original data as possible, before any enrichment with file-level context. This makes it possible to detect drift: if the provider adds fields that the record does not yet capture, comparing `source` to the record payload reveals the gap.
- Keep field values as they appear in the source. Do not pre-compose strings or derive values — that is `transform`'s responsibility.

The record is the stable interface between extract and transform. If the provider's file format changes, only `extract_file` (and the file schema) should need updating — `transform` reads from the record and is insulated from raw format details. The record schema itself should only change when the source gains a field worth exposing to `transform` — not in response to format changes that do not affect what data is available.

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

### Timestamp helpers

When converting a Unix epoch to a timezone-aware `datetime`, use a thin module-level helper rather than inlining the conversion. Do not add ambiguity-resolution logic (e.g. ms-vs-s detection) unless there is evidence from real export data that the provider actually uses mixed formats.

### Storage

- `storage.read(key) → bytes` — read a file in full. Use when the file is not a flat JSON array (envelope object, nested structure); pair with a whole-file schema validated via `model_validate` or `TypeAdapter`.
- `storage.open_stream(key) → BinaryIO` — open a stream without loading the file into memory. Use when the file is a flat JSON array at the root; pair with `ijson.items(stream, "item")` and per-item validation.

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

See `context_use/testing/pipe_test_kit.py`. Subclass it and set class variables:

| Class var | Required | Description |
|-----------|----------|-------------|
| `pipe_class` | yes | The `Pipe` subclass under test |
| `expected_extract_count` | yes | Number of records expected from extract |
| `expected_transform_count` | yes | Number of ThreadRows expected from run |
| `fixture_data` | yes | JSON-serialisable fixture data (loaded in conftest) |
| `fixture_key` | yes | Storage key, e.g. `"archive/path/data.json"` |
| `expected_fibre_kind` | no | If set, auto-asserts all rows have this fibreKind |

When `fixture_data` and `fixture_key` are set, `PipeTestKit` auto-generates the `pipe_fixture`. No override needed.

**Auto-generated conformance tests:** extract type/count, ThreadRow validation (unique_key, provider, interaction_type, version, asat, fibreKind, preview), unique keys, fibre kind (if set), count tracking, ClassVar validation.

**Convenience fixtures** for provider-specific tests:

- `extracted_records` — calls `extract()` with fixture data, returns `list[BaseModel]`
- `transformed_rows` — calls `run()` with fixture data, returns `list[ThreadRow]`

Minimal example:

```python
from context_use.providers.myco.search import MyCoSearchPipe
from context_use.testing import PipeTestKit
from tests.unit.etl.myco.conftest import MYCO_SEARCH_JSON

class TestMyCoSearchPipe(PipeTestKit):
    pipe_class = MyCoSearchPipe
    fixture_data = MYCO_SEARCH_JSON
    fixture_key = "archive/search/results.json"
    expected_extract_count = 4
    expected_transform_count = 4
    expected_fibre_kind = "Search"

    def test_preview_text(self, transformed_rows):
        assert any("python" in r.preview for r in transformed_rows)

    def test_record_has_query(self, extracted_records):
        assert extracted_records[0].query == "python tutorials"
```

Tests that need custom inline data (e.g. edge-case filtering) still accept `tmp_path` directly and build their own storage.

A CI-enforced meta-test (`tests/unit/etl/core/test_pipe_coverage.py`) checks that **every registered pipe** has a corresponding `PipeTestKit` subclass. Adding a new pipe without a test will fail CI.

### Test directory layout

```
tests/unit/etl/
├── core/                           # Pipe base-class, registry, payload tests
│   └── test_pipe_coverage.py       # ← enforces every pipe has tests
├── <provider>/
│   ├── conftest.py                 # fixture data constants
│   └── test_<interaction>.py       # PipeTestKit subclass(es)
└── ...
```

### Fixture Data

Place realistic test data under `tests/fixtures/users/alice/<provider>/<archive_version>/`, mirroring the actual archive directory structure. The fixture JSON should exercise edge cases while staying small enough to reason about.

Load fixture JSON in the provider's `conftest.py` (e.g. `tests/unit/etl/instagram/conftest.py`) and import those constants from the test file.

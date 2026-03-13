# Adding a Data Provider

## Quick Reference

Each new pipe is developed in **three sequential pull requests**. Stop and request feedback after each before proceeding to the next.

### PR 1 — Schema & Fixtures

| Step | File | Action |
|------|------|--------|
| 1 | *(temporary, not committed)* | Collect sample files from one or more real archives |
| 2 | `providers/<prov>/<interaction>/schema.json` | Generate JSON Schema with `genson` (merge multiple samples) |
| 3 | `providers/<prov>/<interaction>/schemas.py` | Generate Pydantic models with `datamodel-codegen` |
| 4 | | Review and adjust generated models per [schema rules](#schema-rules) |
| 5 | `tests/fixtures/users/alice/<prov>/v1/...` | Generate fixture data from the real archive, validate against `schema.json` |

### PR 2 — Extraction

| Step | File | Action |
|------|------|--------|
| 6 | `providers/<prov>/<interaction>/record.py` | Define record model (extract→transform contract) |
| 7 | `providers/<prov>/<interaction>/pipe.py` | Implement `Pipe` subclass with `extract_file()` |
| 8 | `tests/unit/etl/<prov>/test_<type>.py` | Add extraction tests (use `extracted_records` fixture) |

### PR 3 — Transformation

| Step | File | Action |
|------|------|--------|
| 9 | `providers/<prov>/<interaction>/pipe.py` | Implement `transform()`, call `declare_interaction()` at module level |
| 10 | `providers/<prov>/<interaction>/__init__.py` | Import the pipe class so registration fires |
| 11 | `providers/<prov>/__init__.py` | Import the interaction package (one line) |
| 12 | `tests/unit/etl/<prov>/test_<type>.py` | Expand to full `PipeTestKit` suite (fixtures already exist from PR 1) |

If schemas are shared across interaction types within a provider, put them in `providers/<prov>/schemas.py`.

For a **new provider**, also:

| Step | File | Action |
|------|------|--------|
| A | `providers/<prov>/` | Create package (`__init__.py`, shared `schemas.py` if needed, interaction subpackages) |
| B | `providers/__init__.py` | Import the new provider package (one line) so it registers |

No changes to `registry.py` are ever needed.

If the provider needs a new fibre (payload) type, see [Extending Payload Models](#extending-payload-models).

---

Key design rules:

- **Pipe is ET, not ETL.** Load is handled by the `Store`.
- **One Pipe class = one interaction type.** Each subclass handles one kind of data (e.g. stories, reels, DMs).
- **`Pipe.run()` yields `Iterator[ThreadRow]`.** Memory-bounded; the facade collects and persists via `Store.insert_threads()`.
- **`InteractionConfig` = pipe + memory config.** Declared once per interaction type, co-located with the pipe class.
- **Three PRs, three reviews.** Schema → extraction → transformation. Each is a separate PR. Stop and request feedback before proceeding.

---

## ETL Pipeline

### Step 1: Schema Generation (PR 1)

The goal is to produce three version-controlled artifacts from real archive files:

1. **`schema.json`** — a JSON Schema document, the canonical description of the file's structure.
2. **`schemas.py`** — Pydantic models generated from the JSON Schema, used for runtime validation.
3. **Test fixtures** — small, representative samples extracted from the real archive data, validated against `schema.json`.

All three are derived from real archives. This guarantees that schemas describe actual provider data, fixtures conform to those schemas, and pipe tests exercise realistic structures.

#### Collecting samples

Extract the target file from one or more archives. Use at least 2–3 samples from different exports to cover field variations (optional fields, type differences). Samples are temporary and not committed to the repo.

#### Generating JSON Schema with genson

[`genson`](https://github.com/wolverdude/genson) infers a JSON Schema from sample data. When given multiple samples it merges them: fields present in some but not others become non-required, and type unions are created when a field differs across samples.

For **envelope objects** (JSON object at root), run `genson` on the full file(s):

```bash
genson sample1.json sample2.json > providers/acme/bookmarks/schema.json
```

For **flat arrays** (JSON array at root), the schema should describe a **single item**, not the array wrapper. Extract items and pass them individually, or run `genson` on the array and then extract the `items` sub-schema from the result into `schema.json`.

#### Generating Pydantic models with datamodel-code-generator

[`datamodel-code-generator`](https://github.com/koxudaxi/datamodel-code-generator) generates typed Pydantic v2 models from a JSON Schema:

```bash
datamodel-codegen \
  --input providers/acme/bookmarks/schema.json \
  --input-file-type jsonschema \
  --output providers/acme/bookmarks/schemas.py \
  --output-model-type pydantic_v2.BaseModel
```

For providers with a custom base model (e.g. Instagram's `InstagramBaseModel` which fixes broken UTF-8 encoding), use `--base-class` so every generated model inherits from it instead of plain `BaseModel`:

```bash
datamodel-codegen \
  --input providers/instagram/likes/schema.json \
  --input-file-type jsonschema \
  --output providers/instagram/likes/schemas.py \
  --output-model-type pydantic_v2.BaseModel \
  --base-class context_use.providers.instagram.schemas.InstagramBaseModel
```

All schemas can be regenerated at once via `make generate-schemas`, which discovers every `schema.json` and runs `datamodel-codegen` with the correct provider-specific flags.

#### Schema rules

Review and adjust generated models before committing:

- **Optionality**: A field present in all samples may still be optional in real data. Change to `field: T | None = None` when appropriate.
- **Naming**: Rename auto-generated names (e.g. `Model`, `ModelItem`) to follow project conventions (e.g. `BookmarksManifest`, `BookmarkItem`).
- **Nested structures**: Verify nested objects are Pydantic classes, not `dict` or `dict[str, Any]`. Use `dict[str, object] | None` only for genuinely opaque sub-structures the pipe never inspects.
- **Unions**: When a field holds different types (e.g. text parts and attachment parts in the same list), model as a typed union rather than collapsing to a common base.
- **Extra fields**: Keep Pydantic's default of allowing extra fields. Providers add fields over time; schemas must not reject unknown fields. Only the removal or renaming of a field the pipe depends on should cause a validation failure.
- **No `TypeAdapter(list[...])`**: For flat arrays, define only the item model. Streaming handles array iteration.

In practice, follow the Instagram provider as a reference: `InstagramV1ActivityItem` in `providers/instagram/schemas.py` (shared schemas), `InstagramCommentStringMapData` in `providers/instagram/comments/schemas.py`, and `InstagramSavedPostSMD` in `providers/instagram/saved/schemas.py`.

#### Generating test fixtures from real archives

Test fixtures must be derived from the same real archives used to generate the schema — never invented synthetically. This keeps schemas, fixtures, and pipe logic in sync.

1. **Sample**: extract a small, representative subset from the real archive file. Include enough items to cover edge cases (optional fields present/absent, different content types) while staying small enough to reason about. Redact or anonymize PII.
2. **Validate**: validate the fixture against `schema.json`. If validation passes, the fixture is structurally consistent with the schema.
3. **Commit**: place the fixture under `tests/fixtures/users/alice/<provider>/<archive_version>/`, mirroring the actual archive directory structure.

If the fixture fails validation — e.g. because `schema.json` was updated after ingesting a new archive — regenerate the fixture from the current real archive data and re-validate. A fixture that does not pass schema validation must not be committed.

Load fixture JSON in the provider's `conftest.py` (e.g. `tests/unit/etl/instagram/conftest.py`) and import those constants from test files.

#### Keeping schemas and fixtures in sync

When a new archive reveals fields or structures not covered by the current schema:

1. Re-run `genson` with the new archive's sample merged into the existing samples → updated `schema.json`.
2. Regenerate `schemas.py` via `make generate-schemas`.
3. Re-validate existing fixtures against the updated `schema.json`. If they fail, regenerate them from the real archive data.
4. Run tests — if extraction or transformation logic relied on assumptions the schema change invalidated, update the pipe code.

This ensures the chain **real archives → schema → fixtures → tests** never goes stale.

> **⏸ Stop here.** Open a PR with `schema.json`, `schemas.py`, and test fixtures. Request feedback before proceeding to extraction.

---

### Step 2: Extraction (PR 2)

Extraction answers: *what is in this file?* It parses raw files against the generated schemas, validates them, and flattens the validated data into records.

#### The record schema

The record schema is a **contract between `extract_file` and `transform`** — a complete, faithful, flat mirror of the useful raw data for one logical item.

- Include **every source field that could inform the transformation**: content, participants, media references, timestamps, context flags. Omit only fields that are provably irrelevant to any downstream use.
- Include a `source: str | None = None` field that holds the raw source item — as close to the original data as possible, before any enrichment with file-level context. This makes it possible to detect drift: if the provider adds fields that the record does not yet capture, comparing `source` to the record payload reveals the gap.
- Keep field values as they appear in the source. Do not pre-compose strings or derive values — that is `transform`'s responsibility.

The record is the stable interface between extract and transform. If the provider's file format changes, only `extract_file` (and the file schema) should need updating — `transform` reads from the record and is insulated from raw format details. The record schema itself should only change when the source gains a field worth exposing to `transform` — not in response to format changes that do not affect what data is available.

#### Implementing `extract_file`

`extract_file(source_uri, storage) → Iterator[Record]`:

- **Validate first.** Parse the raw file against its schema. This is the breaking-change gate — no transformation will run against a file that fails validation.
- Flatten the validated file's items into records, enriching each with any file-level context (e.g. fields that live at the file root rather than on each individual item).
- Yield one record per logical item — one message, one post, one comment.
- Capture **every field that could plausibly be useful** in `transform`: sender, recipients, timestamps, content text, media URIs, reaction counts, reply context, etc. When in doubt, include it.
- Keep field values as close to the source as possible. Do not compose strings, derive values, or make semantic decisions here.
- Skip only when data is **structurally unusable**: a required field is missing, or there is no renderable content at all.
- Extract filter criteria (role names, content types, etc.) to named module-level constants when they appear in more than one place. Single-use, self-evident values can stay as literals.
- When filtering requires checking multiple conditions, extract a dedicated predicate so the extract loop stays readable. Separate *what records we want* from *whether the record has usable content*; keep data-quality checks inline.

#### Validation by file type

**Envelope objects** (not a flat JSON array at root) must be read in full with `storage.read()` and validated with a file-level schema via `Model.model_validate_json(raw)`. If the file is a JSON object wrapping a list, model the object as a Pydantic class and make the list field `list[ItemModel]` — not `list[dict]`.

**Flat arrays** (array at root) must be streamed with `storage.open_stream()` + `ijson.items(stream, "item")`. There is no whole-file schema — define only the item model and validate each item individually as it is streamed (`ItemModel.model_validate(raw_item)` inside the loop).

#### Strict validation

Validation errors are categorically different from runtime errors. A validation failure means the schema doesn't match the data — this is almost always systemic (affects all files of that type), not a transient per-file issue. The pipe must raise `SchemaValidationError` (wrapping Pydantic's `ValidationError`), which the base `Pipe.extract()` does **not** catch — it propagates through `run()` and the task is marked as failed with the full error detail visible.

Other exceptions (IO errors, transient failures) are caught by `extract()`, logged, and the file is skipped — this is unchanged.

**Do not suppress validation errors.** Silently swallowing errors anywhere (e.g. a try/except around `model_validate` in `extract_file`, or a `field_validator` that catches and returns `None`) hides schema drift and makes it impossible to detect when the provider changes its format.

For **streaming (flat arrays)**, strict validation means fail-fast: on the first item that fails `model_validate`, `SchemaValidationError` propagates immediately. Items already yielded before the failure are discarded (the store does batch insert per task). The tradeoff is that you only see the first bad item's error, not all of them — but schema mismatches are systemic, so the first error tells you what needs fixing.

The error message is the triage signal:
- `missing` on a field the pipe doesn't use → schema too strict, update `schema.json` and regenerate
- `type_error` on a field the pipe uses → input is wrong or schema needs a type fix

#### Storage

- `storage.read(key) → bytes` — for envelope objects. Pair with `model_validate_json`.
- `storage.open_stream(key) → BinaryIO` — for flat arrays. Pair with `ijson.items(stream, "item")` and per-item validation.

> **⏸ Stop here.** Open a PR with `record.py`, the extraction logic in `pipe.py`, and extraction tests (using fixtures from PR 1). Request feedback before proceeding to transformation.

---

### Step 3: Transformation (PR 3)

Transformation answers: *what does this record mean?* It maps each record onto the appropriate fibre model and produces a `ThreadRow`.

#### Implementing `transform`

`transform(record, task) → ThreadRow`:

- Map the record's fields onto the appropriate fibre model. **Use all the information the record carries** — do not silently drop fields that have a place in the payload.
- Apply semantic logic where needed: detect system-generated strings, compose the human-readable content field, choose the right fibre type for variation within the pipe.
- **Do not introduce fields that have no basis in the record.** If a fibre field cannot be populated from the record, leave it unset rather than guessing.
- When building a `Collection` context (e.g. for conversations or threads), set its `id` to the **real, user-facing URL** of the conversation or collection whenever possible. If the archive does not expose the public identifier, construct a stable synthetic URL from the data that is available and **add a comment** explaining that the URL is synthetic and why.
- Build the fibre payload and return a `ThreadRow`.

#### Payload (fibre) models

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

#### Extending payload models

To add a genuinely new fibre type: subclass the appropriate AS base (`Activity` or `Object`) with `_BaseFibreMixin`, add a `fibreKind` literal field, implement `_get_preview()`, call `model_rebuild()` at module level, and add it to the `FibreByType` union at the bottom of the file. The models have to be compliant with [Activity Streams 2.0](https://www.w3.org/TR/activitystreams-core/).

#### Writing previews

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

> **⏸ Stop here.** Open a PR with the `transform()` implementation, `declare_interaction()`, package imports, and the full `PipeTestKit` suite. Request feedback.

---

### Shared Patterns

#### Glob patterns (`archive_path_pattern`)

Uses `fnmatch` syntax relative to the archive root (no archive ID prefix). Patterns with wildcards bundle all matched files into one `EtlTask` via `source_uris` (sorted for determinism). `extract_file` always handles a single file — the base class loops.

#### Timestamp helpers

When converting a Unix epoch to a timezone-aware `datetime`, use a thin module-level helper rather than inlining the conversion. Do not add ambiguity-resolution logic (e.g. ms-vs-s detection) unless there is evidence from real export data that the provider actually uses mixed formats.

#### Shared base class pattern

When a provider has multiple interaction types sharing the same `record_schema` and `transform()`, extract shared logic into a private base class. Only concrete subclasses (which set `interaction_type` and `archive_path_pattern`) get registered. See `context_use/providers/instagram/media/pipe.py`.

#### Versioning via inheritance

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

#### Testing by PR

**PR 2 (Extraction):** Write tests using the `extracted_records` fixture. Verify record count, field values, and edge cases. You may write a partial `PipeTestKit` subclass with `transform()` stubbed, or test `extract_file()` directly.

**PR 3 (Transformation):** Expand to the full `PipeTestKit` suite. Set `expected_extract_count`, `expected_transform_count`, `expected_fibre_kind`. Add provider-specific assertions on previews, payload fields, etc.

A CI-enforced meta-test (`tests/unit/etl/core/test_pipe_coverage.py`) checks that **every registered pipe** has a corresponding `PipeTestKit` subclass. This check applies after PR 3 when `declare_interaction` fires.

### Minimal example

```python
from context_use.providers.myco.search.pipe import MyCoSearchPipe
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

### Test directory layout

```
tests/unit/etl/
├── core/                           # Pipe base-class, registry, payload tests
│   └── test_pipe_coverage.py       # ← enforces every pipe has tests
├── <provider>/
│   ├── conftest.py                 # fixture data constants
│   └── test_<interaction_type>.py  # PipeTestKit subclass(es)
└── ...
```

### Fixture Data

Fixtures are generated from real archive data and validated against `schema.json` as part of [Step 1: Schema Generation](#step-1-schema-generation-pr-1). They live under `tests/fixtures/users/alice/<provider>/<archive_version>/`, mirroring the actual archive directory structure.

Load fixture JSON in the provider's `conftest.py` (e.g. `tests/unit/etl/instagram/conftest.py`) and import those constants from the test file.

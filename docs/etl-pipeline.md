# ETL Pipeline

### Step 1: Schema Generation (PR 1)

The goal is to produce three version-controlled artifacts from real archive files:

1. **`schema.json`** — a JSON Schema document, the canonical description of the file's structure.
2. **`schemas.py`** — Pydantic models generated from the JSON Schema, used for runtime validation.
3. **Test fixtures** — small, representative samples extracted from the real archive data, validated against `schema.json`.

All three are derived from real archives. This guarantees that schemas describe actual provider data, fixtures conform to those schemas, and pipe tests exercise realistic structures.

#### Collecting input files

Use the **whole file** from each archive — not a subset. Many field variations are rare and only surface across a large number of records, so sampling risks missing outliers. Feed complete files from multiple archives into `genson` to maximise coverage. The archive files themselves are not committed to the repo.

#### Generating JSON Schema with genson

[`genson`](https://github.com/wolverdude/genson) infers a JSON Schema from sample data. When given multiple samples it merges them: fields present in some but not others become non-required, and type unions are created when a field differs across samples.

For **envelope objects** (JSON object at root), run `genson` on the full file(s):

```bash
genson sample1.json sample2.json > providers/acme/bookmarks/schema.json
```

For **flat arrays** (JSON array at root), the schema should describe a **single item**, not the array wrapper. Extract items and pass them individually, or run `genson` on the array and then extract the `items` sub-schema from the result into `schema.json`.

#### Reviewing and adjusting schema.json

`schema.json` is the **single source of truth**. `schemas.py` is always a deterministic, mechanical output of it — never edited by hand. All structural decisions must be encoded in `schema.json` first; `schemas.py` is then regenerated.

After `genson` produces the initial schema, review it and make targeted adjustments where the inferred schema is too strict or too specific for real-world data:

- **Optionality**: Only remove a field from `required` when there is evidence it can be absent — e.g. it is missing in at least one of the archives fed to `genson`, or you have strong reason to believe it may not appear in archives you do not have. Do not speculatively mark fields as optional.
- **Opaque sub-structures**: For fields the pipe never inspects, simplify their schema to `{"type": "object"}` (no `properties`, no `required`). This avoids false validation failures when those sub-structures evolve. `genson` over-specifies them from the sample data.
- **Unconstrained nullable fields**: Fields that appear as `{"type": "null"}` in the generated schema have only been observed as `null` across all samples. Replace them with `{}` (unconstrained) so validation does not fail if the provider starts returning a real value there.
- **Unions**: When a field genuinely holds different types across the sample data, `genson` produces a `anyOf` or type array. Keep these — they reflect reality.
- **Extra fields**: Do not add `"additionalProperties": false`. Providers add fields over time; unknown fields must be silently accepted.
- **No `items` wrapper**: For flat arrays, the schema describes a single item. Do not wrap it in an array schema.

Do not touch anything else. Every other aspect of the generated schema — field names, nesting depth, required sets for well-evidenced fields — must remain exactly as `genson` produced it.

If you decide to generalise the schema beyond the adjustments listed above — for example, widening a type, collapsing a sub-structure further than the "opaque sub-structures" rule requires, or removing a required field without direct evidence from the sample archives — the PR must explicitly call out each such decision and explain the reasoning: what evidence or constraint motivated the change, and why the standard rules were insufficient.

#### Generating schemas.py with datamodel-code-generator

Once `schema.json` is finalised, generate `schemas.py` deterministically:

```bash
datamodel-codegen \
  --input providers/acme/bookmarks/schema.json \
  --input-file-type jsonschema \
  --output providers/acme/bookmarks/schemas.py \
  --output-model-type pydantic_v2.BaseModel \
  --formatters ruff-format ruff-check
```

Do not use `--base-class`. Provider-specific data quirks (e.g. Instagram's broken UTF-8 encoding) must be handled in `extract_file`, not in the schema model. Applying a fix inside a `@model_validator` bakes extraction logic into a structural class and requires the generator to know about a provider-specific base — coupling two layers that should be independent. Instead, fix the raw data before calling `model_validate`:

```python
for raw_item in ijson.items(stream, "item"):
    item = InstagramLikesItem.model_validate(_fix_strings_recursive(raw_item))
```

Schema models answer one question: *does this data have the right shape?* They must not encode *how to read* the data correctly.

**`schemas.py` must always be in sync with `schema.json`.** If a structural change is needed — a field becomes optional, a sub-structure is simplified, a type is widened — make the change in `schema.json` and regenerate. Never edit `schemas.py` by hand to fix a structural issue.

##### schemas.py is read-only after generation

Do not edit `schemas.py` after generation. `schemas.py` contains only what the generator produces.

Unconstrained fields (`{}` in JSON Schema) generate `Any` in Python. This is the only case where `Any` appears in `schemas.py`: it directly reflects that the field has only been observed as `null` across all available archives, and there is not yet enough evidence to assert a more specific type. If future archives reveal a consistent structure, replace `{}` with a concrete schema and regenerate.


#### Generating test fixtures from real archives

Test fixtures must be derived from the same real archives used to generate the schema — never invented synthetically. This keeps schemas, fixtures, and pipe logic in sync.

1. **Sample**: extract a small, representative subset from the real archive file. Include enough items to cover edge cases (optional fields present/absent, different content types) while staying small enough to reason about. Redact or anonymize PII.
2. **Validate**: validate the fixture against `schema.json`. If validation passes, the fixture is structurally consistent with the schema.
3. **Commit**: place the fixture under `tests/fixtures/users/alice/<provider>/<archive_version>/`, mirroring the actual archive directory structure.

If the fixture fails validation — e.g. because `schema.json` was updated after ingesting a new archive — regenerate the fixture from the current real archive data and re-validate. A fixture that does not pass schema validation must not be committed.

Load fixture JSON in the provider's `conftest.py` (e.g. `tests/unit/etl/instagram/conftest.py`) and import those constants from test files.

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

> Sent message "hey, when are you free?" to alice on Instagram
> Received message "Sure! Here are a few options..." from assistant on ChatGPT
> Posted image on Instagram with caption: "Team at work"
> Viewed page "Best pasta recipes - BBC Good Food" via Google
> Liked post by janedoe on Instagram
> Commented "this is amazing!" on alice's post on Instagram
> Searched "best restaurants nearby" on Google
> Saved to "Trip Ideas" post by traveler on Instagram
> Following bob on Instagram
> Followed by alice on Instagram

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

# Step 2: Extraction (PR 2)

Extraction answers: *what is in this file?* It parses raw files against the generated schemas, validates them, and flattens the validated data into records.

## The record schema

The record schema is a **contract between `extract_file` and `transform`** — a complete, faithful, flat mirror of the useful raw data for one logical item.

- Include **every source field that could inform the transformation**: content, participants, media references, timestamps, context flags. Omit only fields that are provably irrelevant to any downstream use.
- Include a `source: str | None = None` field that holds the raw source item — as close to the original data as possible, before any enrichment with file-level context. This makes it possible to detect drift: if the provider adds fields that the record does not yet capture, comparing `source` to the record payload reveals the gap.
- Keep field values as they appear in the source. Do not pre-compose strings or derive values — that is `transform`'s responsibility.

The record is the stable interface between extract and transform. If the provider's file format changes, only `extract_file` (and the file schema) should need updating — `transform` reads from the record and is insulated from raw format details. The record schema itself should only change when the source gains a field worth exposing to `transform` — not in response to format changes that do not affect what data is available.

## Implementing `extract_file`

`extract_file(source_uri, storage) → Iterator[Record]`:

- **Validate first.** Parse the raw file against its schema. This is the breaking-change gate — no transformation will run against a file that fails validation.
- Flatten the validated file's items into records, enriching each with any file-level context (e.g. fields that live at the file root rather than on each individual item).
- Yield one record per logical item — one message, one post, one comment.
- Capture **every field that could plausibly be useful** in `transform`: sender, recipients, timestamps, content text, media URIs, reaction counts, reply context, etc. When in doubt, include it.
- Keep field values as close to the source as possible. Do not compose strings, derive values, or make semantic decisions here.
- Skip only when data is **structurally unusable**: a required field is missing, or there is no renderable content at all.
- Extract filter criteria (role names, content types, etc.) to named module-level constants when they appear in more than one place. Single-use, self-evident values can stay as literals.
- When filtering requires checking multiple conditions, extract a dedicated predicate so the extract loop stays readable. Separate *what records we want* from *whether the record has usable content*; keep data-quality checks inline.

## Validation by file type

**Envelope objects** (not a flat JSON array at root) must be read in full with `storage.read()` and validated with a file-level schema via `Model.model_validate_json(raw)`. If the file is a JSON object wrapping a list, model the object as a Pydantic class and make the list field `list[ItemModel]` — not `list[dict]`.

**Flat arrays** (array at root) must be streamed with `storage.open_stream()` + `ijson.items(stream, "item")`. There is no whole-file schema — define only the item model and validate each item individually as it is streamed (`ItemModel.model_validate(raw_item)` inside the loop).

## Strict validation

Validation errors are categorically different from runtime errors. A validation failure means the schema doesn't match the data — this is almost always systemic (affects all files of that type), not a transient per-file issue. The pipe must raise `SchemaValidationError` (wrapping Pydantic's `ValidationError`), which the base `Pipe.extract()` does **not** catch — it propagates through `run()` and the task is marked as failed with the full error detail visible.

Other exceptions (IO errors, transient failures) are caught by `extract()`, logged, and the file is skipped — this is unchanged.

**Do not suppress validation errors.** Silently swallowing errors anywhere (e.g. a try/except around `model_validate` in `extract_file`, or a `field_validator` that catches and returns `None`) hides schema drift and makes it impossible to detect when the provider changes its format.

For **streaming (flat arrays)**, strict validation means fail-fast: on the first item that fails `model_validate`, `SchemaValidationError` propagates immediately. Items already yielded before the failure are discarded (the store does batch insert per task). The tradeoff is that you only see the first bad item's error, not all of them — but schema mismatches are systemic, so the first error tells you what needs fixing.

The error message is the triage signal:
- `missing` on a field the pipe doesn't use → schema too strict, update `schema.json` and regenerate
- `type_error` on a field the pipe uses → input is wrong or schema needs a type fix

## Storage

- `storage.read(key) → bytes` — for envelope objects. Pair with `model_validate_json`.
- `storage.open_stream(key) → BinaryIO` — for flat arrays. Pair with `ijson.items(stream, "item")` and per-item validation.

> **⏸ Stop here.** Open a PR with `record.py`, the extraction logic in `pipe.py`, and extraction tests (using fixtures from PR 1). Request feedback before proceeding to transformation.

# Step 1: Schema Generation (PR 1)

The goal is to produce three version-controlled artifacts from real archive files:

1. **`schema.json`** — a JSON Schema document, the canonical description of the file's structure.
2. **`schemas.py`** — Pydantic models generated from the JSON Schema, used for runtime validation.
3. **Test fixtures** — small, representative samples extracted from the real archive data, validated against `schema.json`.

All three are derived from real archives. This guarantees that schemas describe actual provider data, fixtures conform to those schemas, and pipe tests exercise realistic structures.

## Collecting input files

Use the **whole file** from each archive — not a subset. Many field variations are rare and only surface across a large number of records, so sampling risks missing outliers. Feed complete files from multiple archives into `genson` to maximise coverage. The archive files themselves are not committed to the repo.

## Generating JSON Schema with genson

[`genson`](https://github.com/wolverdude/genson) infers a JSON Schema from sample data. When given multiple samples it merges them: fields present in some but not others become non-required, and type unions are created when a field differs across samples.

For **envelope objects** (JSON object at root), run `genson` on the full file(s):

```bash
genson sample1.json sample2.json > providers/acme/bookmarks/schema.json
```

For **flat arrays** (JSON array at root), the schema should describe a **single item**, not the array wrapper. Extract items and pass them individually, or run `genson` on the array and then extract the `items` sub-schema from the result into `schema.json`.

## Reviewing and adjusting schema.json

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

## Generating schemas.py with datamodel-code-generator

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

### schemas.py is read-only after generation

Do not edit `schemas.py` after generation. `schemas.py` contains only what the generator produces. Do not restructure `schema.json` (e.g. with `$defs` or `title` fields) to influence the generated class names — accept whatever names `datamodel-codegen` assigns.

Unconstrained fields (`{}` in JSON Schema) generate `Any` in Python. This is the only case where `Any` appears in `schemas.py`: it directly reflects that the field has only been observed as `null` across all available archives, and there is not yet enough evidence to assert a more specific type. If future archives reveal a consistent structure, replace `{}` with a concrete schema and regenerate.


## Generating test fixtures from real archives

Test fixtures must be derived from the same real archives used to generate the schema — never invented synthetically. This keeps schemas, fixtures, and pipe logic in sync.

1. **Sample**: extract a small, representative subset from the real archive file. Include enough items to cover edge cases (optional fields present/absent, different content types) while staying small enough to reason about. Redact or anonymize PII.
2. **Validate**: validate the fixture against `schema.json`. If validation passes, the fixture is structurally consistent with the schema.
3. **Commit**: place the fixture under `tests/fixtures/users/alice/<provider>/<archive_version>/`, mirroring the actual archive directory structure.

If the fixture fails validation — e.g. because `schema.json` was updated after ingesting a new archive — regenerate the fixture from the current real archive data and re-validate. A fixture that does not pass schema validation must not be committed.

Load fixture JSON in the provider's `conftest.py` (e.g. `tests/unit/etl/instagram/conftest.py`) and import those constants from test files.

> **⏸ Stop here.** Open a PR with `schema.json`, `schemas.py`, and test fixtures. Request feedback before proceeding to extraction.

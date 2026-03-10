---
name: context-use-etl
description: >
  Triggered when adding, modifying, or debugging ETL pipes and providers
  in the context-use codebase — including record schemas, payload
  construction, memory config, fixture data, and PipeTestKit tests.
user-invocable: true
---

# context-use ETL Skill

## When to Use

Use this skill when the task involves any of:

- Adding a new ETL pipe to an **existing** provider.
- Creating a **new** provider package from scratch.
- Extending or fixing an existing pipe's `extract_file()` or `transform()`.
- Adding or modifying a Fibre payload model.
- Writing or updating `PipeTestKit` tests and fixture data.
- Wiring up memory config (grouper + prompt builder) for a pipe.

Do **not** use this skill for changes that are purely in the memory pipeline
(prompt builders, groupers, batch manager) with no ETL involvement — those
follow their own conventions.

## Required Inputs

Before starting, confirm or gather:

1. **Provider name** — existing (`chatgpt`, `claude`, `google`, `instagram`) or new.
2. **Interaction type** — kebab-style identifier (e.g. `instagram_liked_posts`).
3. **Archive path** — relative path inside the ZIP export where the source data lives. Obtain a sample of the raw JSON.
4. **Archive version** — integer; `1` for a first-time pipe, bumped for format changes.
5. **Payload type** — which Fibre model to use (`FibreSendMessage`, `FibreReceiveMessage`, `FibreCreateObject`, `FibreLike`, `FibreViewObject`, `FibreSearch`, etc.). Check existing types in `context_use/etl/payload/models.py` before creating a new one.
6. **Memory config** — whether the pipe needs memory generation, and if so which grouper (`WindowGrouper` or `CollectionGrouper`) and prompt builder (`ConversationMemoryPromptBuilder` or `MediaMemoryPromptBuilder`). Set to `None` if memories are not needed yet.

## Step-by-Step Workflow

### A. New pipe on an existing provider

#### 1. Add record schema(s)

File: `context_use/providers/<provider>/schemas.py`

- Add a Pydantic `BaseModel` subclass for the extracted record.
- Include a `source: str | None = None` field.
- Reuse or extend existing base schemas in the same file when possible (e.g. Instagram has `InstagramBaseModel` with a mojibake fix).

#### 2. Create the pipe module

File: `context_use/providers/<provider>/<module>.py`

- Import `Pipe` from `context_use.etl.core.pipe`.
- Import `ThreadRow` from `context_use.etl.core.types`.
- Import `CURRENT_THREAD_PAYLOAD_VERSION` and the appropriate Fibre model(s) from `context_use.etl.payload.models`.
- Import `PROVIDER` from the provider's `schemas.py`.
- Import `declare_interaction` from `context_use.providers.registry` and `InteractionConfig` from `context_use.providers.types`.
- Subclass `Pipe[YourRecord]` and set all required ClassVars:
  - `provider = PROVIDER`
  - `interaction_type = "<provider>_<type>"`
  - `archive_version = <int>`
  - `archive_path_pattern = "<relative/path/in/archive>"`
  - `record_schema = YourRecord`
- Implement `extract_file(self, source_uri, storage)`:
  - Use `storage.read(source_uri)` for small JSON files, or `storage.open_stream(source_uri)` with `ijson` for large files.
  - Yield one validated Pydantic record per logical item.
  - Filter irrelevant records here (not in `transform()`).
  - Stash raw JSON in `record.source = json.dumps(raw_item)`.
- Implement `transform(self, record, task)`:
  - Build a Fibre payload (e.g. `FibreLike`, `FibreCreateObject`).
  - Return a `ThreadRow` with: `unique_key=payload.unique_key()`, `provider=self.provider`, `interaction_type=self.interaction_type`, `preview=payload.get_preview(task.provider) or ""`, `payload=payload.to_dict()`, `source=record.source`, `version=CURRENT_THREAD_PAYLOAD_VERSION`, `asat=<datetime>`.
  - For media pipes, also set `asset_uri=f"{task.archive_id}/{record.uri}"`.
- At module level, call `declare_interaction(InteractionConfig(pipe=YourPipe, memory=<MemoryConfig or None>))` for each concrete pipe class.
- When multiple pipes share `record_schema` and `transform()`, use the shared base class pattern: create a private `_BaseXxxPipe` with shared logic, then concrete subclasses that only set `interaction_type`, `archive_path_pattern`, and implement `extract_file()`.

#### 3. Register the module

File: `context_use/providers/<provider>/__init__.py`

- Add one import line for the new module.
- Add the module to the `modules=[...]` list in the `register_provider()` call.

#### 4. Add fixture data

Directory: `tests/fixtures/users/alice/<provider>/v<version>/`

- Mirror the actual archive directory structure.
- Create realistic but small JSON fixture data that exercises edge cases.
- Add the fixture constant to `tests/conftest.py` following the existing pattern (load JSON from the fixture path).

#### 5. Write tests

File: `tests/unit/etl/test_<provider>_<type>.py`

- Import the pipe class, `DiskStorage`, `PipeTestKit`, and the fixture constant from `tests.conftest`.
- Subclass `PipeTestKit` and set:
  - `pipe_class` — the concrete `Pipe` subclass.
  - `expected_extract_count` — number of records `extract()` should yield from the fixture.
  - `expected_transform_count` — number of `ThreadRow`s `run()` should yield.
- Implement the `pipe_fixture` pytest fixture:
  - `storage = DiskStorage(str(tmp_path / "store"))`
  - `key = "archive/<archive_path_pattern>"`
  - `storage.write(key, json.dumps(FIXTURE_CONSTANT).encode())`
  - `return storage, key`
- Add provider-specific test methods that verify:
  - Record field values from `extract()`.
  - Payload `fibreKind`, `type`, and nested object structure from `run()`.
  - `preview` content.
  - `asat` correctness.
  - `interaction_type` on each row.
  - `asset_uri` for media pipes.
  - Edge cases (missing fields, filtered records, etc.).

#### 6. Verify

```bash
uv run pytest tests/unit/etl/test_<provider>_<type>.py -v
uv run pytest -m "not integration"
uv run pyright
uv run ruff check --fix
uv run ruff format
```

### B. New provider

Complete steps A.1–A.6 above, plus:

#### B.1. Create the provider package

- `context_use/providers/<provider>/__init__.py` — import submodules, call `register_provider(PROVIDER, modules=[...])`.
- `context_use/providers/<provider>/schemas.py` — define `PROVIDER = "<name>"` and record models.
- One or more pipe modules.

#### B.2. Register the provider

File: `context_use/providers/__init__.py`

- Add one import line for the new provider package.

### C. New Fibre payload type

Only if no existing Fibre type fits. Check `context_use/etl/payload/models.py` first.

1. Subclass the appropriate ActivityStreams base (`Activity` or `Object`) with `_BaseFibreMixin`.
2. Add a `fibreKind: Literal["YourKind"]` field.
3. Implement `_get_preview(self, provider)` returning a human-readable string.
4. Call `model_rebuild()` at module level after the class definition.
5. Add the new type to the `FibreByType` discriminated union at the bottom of the file.

### D. Versioning via inheritance

When a provider ships a new archive format:

1. **Do not edit the existing pipe.** Subclass it.
2. Override `extract_file()` (and `extract()` if needed).
3. Set a new `archive_version` and `archive_path_pattern`.
4. `transform()` is inherited when `record_schema` stays the same.

## Output Format

After completing the workflow, the result should include:

| File | Change |
|------|--------|
| `context_use/providers/<provider>/schemas.py` | New/modified record model(s) |
| `context_use/providers/<provider>/<module>.py` | New `Pipe` subclass + `declare_interaction()` |
| `context_use/providers/<provider>/__init__.py` | Import + registration |
| `tests/fixtures/users/alice/<provider>/v<N>/...` | Fixture JSON |
| `tests/conftest.py` | Fixture constant |
| `tests/unit/etl/test_<provider>_<type>.py` | `PipeTestKit` subclass + specific tests |

For a new provider, also:

| File | Change |
|------|--------|
| `context_use/providers/<provider>/` | New package |
| `context_use/providers/__init__.py` | Import line |

## Error Handling & Stop Conditions

- **No matching Fibre type:** Stop and create a new one (Section C) before continuing.
- **Fixture data unavailable:** Ask for a sample of the raw archive JSON. Do not fabricate fixture data without seeing the actual format.
- **Tests fail on `test_run_yields_well_formed_thread_rows`:** The payload is malformed. Verify `fibreKind` is set, `unique_key` is non-empty, `preview` is non-empty, `asat` is a `datetime`, and `payload` is a dict.
- **`register_provider` raises `ValueError`:** The module was imported in `__init__.py` but has no `declare_interaction()` call. Ensure every pipe module calls `declare_interaction()` at module level.
- **`pyright` errors on Fibre construction:** Fibre models use `# type: ignore[reportCallIssue]` on construction calls — this is an accepted pattern in the codebase.
- **Duplicate `unique_key` in tests:** The `unique_key` is a content hash. If two records produce the same hash, the fixture data contains true duplicates or the payload is not capturing enough distinguishing fields.

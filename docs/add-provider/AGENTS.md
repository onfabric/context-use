# Adding a Data Provider

## Quick Reference

Each new pipe is developed in **three sequential pull requests**. Stop and request feedback after each before proceeding to the next.

### PR 1 — Schema & Fixtures ([details](1-schema-generation.md))

| Step | File | Action |
|------|------|--------|
| 1 | *(temporary, not committed)* | Collect sample files from one or more real archives |
| 2 | `providers/<prov>/<interaction>/schema.json` | Generate JSON Schema with `genson` (merge multiple samples) |
| 3 | `providers/<prov>/<interaction>/schemas.py` | Generate Pydantic models with `datamodel-codegen` |
| 4 | | Review and adjust generated models per [schema rules](1-schema-generation.md#reviewing-and-adjusting-schemajson) |
| 5 | `tests/fixtures/users/alice/<prov>/v1/...` | Generate fixture data from the real archive, validate against `schema.json` |

### PR 2 — Extraction ([details](2-extraction.md))

| Step | File | Action |
|------|------|--------|
| 6 | `providers/<prov>/<interaction>/record.py` | Define record model (extract→transform contract) |
| 7 | `providers/<prov>/<interaction>/pipe.py` | Implement `Pipe` subclass with `extract_file()` |
| 8 | `tests/unit/etl/<prov>/test_<type>.py` | Add extraction tests — see [Testing](#testing) |

### PR 3 — Transformation ([details](3-transformation.md))

| Step | File | Action |
|------|------|--------|
| 9 | `providers/<prov>/<interaction>/pipe.py` | Implement `transform()`, call `declare_interaction()` at module level |
| 10 | `providers/<prov>/<interaction>/__init__.py` | Import the pipe class so registration fires |
| 11 | `providers/<prov>/__init__.py` | Import the interaction package (one line) |
| 12 | `tests/unit/etl/<prov>/test_<type>.py` | Expand to full `PipeTestKit` suite — see [Testing](#testing) (fixtures already exist from PR 1) |

If schemas are shared across interaction types within a provider, put them in `providers/<prov>/schemas.py`.

For a **new provider**, also:

| Step | File | Action |
|------|------|--------|
| A | `providers/<prov>/` | Create package (`__init__.py`, shared `schemas.py` if needed, interaction subpackages) |
| B | `providers/__init__.py` | Import the new provider package (one line) so it registers |

No changes to `registry.py` are ever needed.

If the provider needs a new fibre (payload) type, see [Extending Payload Models](3-transformation.md#extending-payload-models).

---

## Key Design Rules

- **Pipe is ET, not ETL.** Load is handled by the `Store`.
- **One Pipe class = one interaction type.** Each subclass handles one kind of data (e.g. stories, reels, DMs).
- **`Pipe.run()` yields `Iterator[ThreadRow]`.** Memory-bounded; the facade collects and persists via `Store.insert_threads()`.
- **`InteractionConfig` = pipe + memory config.** Declared once per interaction type, co-located with the pipe class.
- **Three PRs, three reviews.** Schema → extraction → transformation. Each is a separate PR. Stop and request feedback before proceeding.

---

## Shared Patterns

### Glob patterns (`archive_path_pattern`)

Uses `fnmatch` syntax relative to the archive root (no archive ID prefix). Patterns with wildcards bundle all matched files into one `EtlTask` via `source_uris` (sorted for determinism). `extract_file` always handles a single file — the base class loops.

### Timestamp helpers

When converting a Unix epoch to a timezone-aware `datetime`, use a thin module-level helper rather than inlining the conversion. Do not add ambiguity-resolution logic (e.g. ms-vs-s detection) unless there is evidence from real export data that the provider actually uses mixed formats.

### Shared base class pattern

When a provider has multiple interaction types sharing the same `record_schema` and `transform()`, extract shared logic into a private base class. Only concrete subclasses (which set `interaction_type` and `archive_path_pattern`) get registered. See `context_use/providers/instagram/media/pipe.py`.

### Versioning via inheritance

To support a new archive format, subclass the existing pipe, override `extract_file()`, and set a new `archive_version` / `archive_path_pattern`. `transform()` is inherited when `record_schema` is unchanged.

`archive_version` tracks the provider's export format. `ThreadRow.version` tracks the payload schema version (`CURRENT_THREAD_PAYLOAD_VERSION`). They are independent.

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

### Testing by PR

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

Fixtures are generated from real archive data and validated against `schema.json` as part of [Step 1: Schema Generation](1-schema-generation.md). They live under `tests/fixtures/users/alice/<provider>/<archive_version>/`, mirroring the actual archive directory structure.

Load fixture JSON in the provider's `conftest.py` (e.g. `tests/unit/etl/instagram/conftest.py`) and import those constants from the test file.

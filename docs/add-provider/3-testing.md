# Testing

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

Fixtures are generated from real archive data and validated against `schema.json` as part of [Step 1: Schema Generation](1-etl-pipeline.md#step-1-schema-generation-pr-1). They live under `tests/fixtures/users/alice/<provider>/<archive_version>/`, mirroring the actual archive directory structure.

Load fixture JSON in the provider's `conftest.py` (e.g. `tests/unit/etl/instagram/conftest.py`) and import those constants from the test file.

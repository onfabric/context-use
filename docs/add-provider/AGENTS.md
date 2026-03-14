# Adding a Data Provider

## Quick Reference

Each new pipe is developed in **three sequential pull requests**. Stop and request feedback after each before proceeding to the next.

### PR 1 — Schema & Fixtures ([details](1-etl-pipeline.md#step-1-schema-generation-pr-1))

| Step | File | Action |
|------|------|--------|
| 1 | *(temporary, not committed)* | Collect sample files from one or more real archives |
| 2 | `providers/<prov>/<interaction>/schema.json` | Generate JSON Schema with `genson` (merge multiple samples) |
| 3 | `providers/<prov>/<interaction>/schemas.py` | Generate Pydantic models with `datamodel-codegen` |
| 4 | | Review and adjust generated models per [schema rules](1-etl-pipeline.md#schema-rules) |
| 5 | `tests/fixtures/users/alice/<prov>/v1/...` | Generate fixture data from the real archive, validate against `schema.json` |

### PR 2 — Extraction ([details](1-etl-pipeline.md#step-2-extraction-pr-2))

| Step | File | Action |
|------|------|--------|
| 6 | `providers/<prov>/<interaction>/record.py` | Define record model (extract→transform contract) |
| 7 | `providers/<prov>/<interaction>/pipe.py` | Implement `Pipe` subclass with `extract_file()` |
| 8 | `tests/unit/etl/<prov>/test_<type>.py` | Add extraction tests — see [Testing](3-testing.md) |

### PR 3 — Transformation ([details](1-etl-pipeline.md#step-3-transformation-pr-3))

| Step | File | Action |
|------|------|--------|
| 9 | `providers/<prov>/<interaction>/pipe.py` | Implement `transform()`, call `declare_interaction()` at module level |
| 10 | `providers/<prov>/<interaction>/__init__.py` | Import the pipe class so registration fires |
| 11 | `providers/<prov>/__init__.py` | Import the interaction package (one line) |
| 12 | `tests/unit/etl/<prov>/test_<type>.py` | Expand to full `PipeTestKit` suite — see [Testing](3-testing.md) (fixtures already exist from PR 1) |

If schemas are shared across interaction types within a provider, put them in `providers/<prov>/schemas.py`.

For a **new provider**, also:

| Step | File | Action |
|------|------|--------|
| A | `providers/<prov>/` | Create package (`__init__.py`, shared `schemas.py` if needed, interaction subpackages) |
| B | `providers/__init__.py` | Import the new provider package (one line) so it registers |

No changes to `registry.py` are ever needed.

If the provider needs a new fibre (payload) type, see [Extending Payload Models](1-etl-pipeline.md#extending-payload-models).

---

Key design rules:

- **Pipe is ET, not ETL.** Load is handled by the `Store`.
- **One Pipe class = one interaction type.** Each subclass handles one kind of data (e.g. stories, reels, DMs).
- **`Pipe.run()` yields `Iterator[ThreadRow]`.** Memory-bounded; the facade collects and persists via `Store.insert_threads()`.
- **`InteractionConfig` = pipe + [memory config](2-memory-pipeline.md).** Declared once per interaction type, co-located with the pipe class.
- **Three PRs, three reviews.** Schema → extraction → transformation. Each is a separate PR. Stop and request feedback before proceeding.

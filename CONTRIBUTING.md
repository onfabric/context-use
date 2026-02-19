# Contributing a New Pipe

This guide walks you through adding a new ETL pipe to context-use. A **Pipe** encapsulates Extract + Transform for a single interaction type (e.g. Instagram DMs, ChatGPT conversations). The Load step is handled separately by a `Loader`.

---

## Quick Reference — Checklist

For a new pipe in an **existing** provider (e.g. adding messages to `instagram`):

| Step | File | Action |
|------|------|--------|
| 1 | `context_use/etl/providers/<provider>/schemas.py` | Add Pydantic record model(s) |
| 2 | `context_use/etl/providers/<provider>/<module>.py` | Create `Pipe` subclass with `extract()` + `transform()` |
| 3 | `context_use/etl/providers/registry.py` | Add pipe class to `ProviderConfig.pipes` list |
| 4 | `tests/fixtures/users/alice/<provider>/v1/...` | Add fixture data (real archive structure) |
| 5 | `tests/test_<provider>_<type>.py` | Subclass `PipeTestKit` + add provider-specific tests |

For a **new** provider, also:

| Step | File | Action |
|------|------|--------|
| A | `context_use/etl/providers/<provider>/` | Create package (`__init__.py`, `schemas.py`, pipe module) |
| B | `context_use/etl/providers/registry.py` | Add `Provider` enum member + `ProviderConfig` entry |

If the provider needs a new fibre (payload) type, see [Extending Payload Models](#extending-payload-models).

---

## Worked Example — Instagram Messages Pipe

This walkthrough adds an `InstagramMessagesPipe` that processes Instagram DM conversations from files matching `your_instagram_activity/messages/inbox/*/message_1.json`.

### Step 1: Define the Record Schema

The record schema is the Pydantic model that `extract()` yields. It represents one parsed item from the archive — here, one chat message.

Create or extend `context_use/etl/providers/instagram/schemas.py`:

```python
class InstagramDirectMessage(BaseModel):
    """One message from an Instagram DM conversation."""

    sender_name: str
    timestamp_ms: int
    content: str
    thread_path: str
    thread_title: str
    source: str | None = None
```

**Rules for record schemas:**

- Must extend `pydantic.BaseModel`.
- Include a `source: str | None = None` field so `transform()` can stash the raw JSON for audit/debug.
- Name it descriptively — the class name appears in test output.

### Step 2: Create the Pipe Subclass

Create `context_use/etl/providers/instagram/messages.py`:

```python
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.models.etl_task import EtlTask
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    Application,
    FibreReceiveMessage,
    FibreSendMessage,
    FibreTextMessage,
    Collection,
)
from context_use.etl.providers.instagram.schemas import InstagramDirectMessage
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class InstagramMessagesPipe(Pipe[InstagramDirectMessage]):
    """ETL pipe for Instagram DM conversations.

    Each invocation processes one ``message_1.json`` file (one conversation).
    The glob pattern fans out to one EtlTask per conversation directory.
    """

    provider = "instagram"
    interaction_type = "instagram_messages"
    archive_version = "v1"
    archive_path_pattern = "your_instagram_activity/messages/inbox/*/message_1.json"
    record_schema = InstagramDirectMessage

    def extract(
        self,
        task: EtlTask,
        storage: StorageBackend,
    ) -> Iterator[InstagramDirectMessage]:
        raw = storage.read(task.source_uri)
        data = json.loads(raw)

        thread_path = data.get("thread_path", "")
        thread_title = data.get("title", "")

        for msg in data.get("messages", []):
            content = msg.get("content")
            if not content:
                continue
            yield InstagramDirectMessage(
                sender_name=msg["sender_name"],
                timestamp_ms=msg["timestamp_ms"],
                content=content,
                thread_path=thread_path,
                thread_title=thread_title,
                source=json.dumps(msg, default=str),
            )

    def transform(
        self,
        record: InstagramDirectMessage,
        task: EtlTask,
    ) -> ThreadRow:
        # ... build payload, return ThreadRow ...
```

#### Required ClassVars

Every `Pipe` subclass **must** set these five class variables:

| ClassVar | Type | Description |
|----------|------|-------------|
| `provider` | `str` | Provider identifier (`"chatgpt"`, `"instagram"`, …) |
| `interaction_type` | `str` | Unique interaction type (`"instagram_messages"`) |
| `archive_version` | `str` | Archive format version, typically `"v1"` |
| `archive_path_pattern` | `str` | `fnmatch` glob for the file path inside the archive |
| `record_schema` | `type[BaseModel]` | The Pydantic model matching the type parameter `Record` |

#### `extract()` Contract

- **Input:** `EtlTask` (provides `source_uri` — the storage key for the file) and `StorageBackend`.
- **Output:** `Iterator[Record]` — yield one validated Pydantic model per logical item.
- Read from `storage.read(task.source_uri)` (for small files) or `storage.open_stream(task.source_uri)` (for streaming/large files like `conversations.json`).
- Filter bad/irrelevant records here — don't push that into `transform()`.

#### `transform()` Contract

- **Input:** one `Record` (from `extract()`) and the `EtlTask`.
- **Output:** one `ThreadRow`.
- Build an ActivityStreams payload (a Fibre model from `context_use.etl.payload.models`).
- Call `payload.to_dict()` for the `payload` field, `payload.get_preview(provider)` for `preview`, and `payload.unique_key_suffix()` for the key suffix.
- Set `unique_key` as `f"{self.interaction_type}:{suffix}"`.
- Set `version` to `CURRENT_THREAD_PAYLOAD_VERSION`.
- Set `asat` to the record's timestamp (as a timezone-aware `datetime`).

#### `run()` — Do Not Override

`run()` is a template method on the base class. It calls `extract()`, then `transform()` for each record, tracks `extracted_count` / `transformed_count`, and yields `ThreadRow` instances lazily. Do not override it.

### Step 3: Register the Pipe

Edit `context_use/etl/providers/registry.py`:

```python
from context_use.etl.providers.instagram.messages import InstagramMessagesPipe

# In PROVIDER_REGISTRY:
Provider.INSTAGRAM: ProviderConfig(
    pipes=[InstagramStoriesPipe, InstagramReelsPipe, InstagramMessagesPipe],
),
```

Every pipe must appear in exactly one `ProviderConfig.pipes` list. The registry uses `archive_path_pattern` for task discovery and `interaction_type` for pipe lookup.

### Step 4: Add Fixture Data

Place realistic test data under `tests/fixtures/users/alice/<provider>/<archive_version>/`. Mirror the actual archive directory structure:

```
tests/fixtures/users/alice/instagram/v1/
  your_instagram_activity/
    messages/
      inbox/
        bobsmith_1234567890/
          message_1.json
```

The fixture JSON should exercise edge cases (multiple message types, empty content, etc.) while staying small enough to reason about.

### Step 5: Write Tests

Create `tests/test_instagram_messages.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_use.etl.providers.instagram.messages import InstagramMessagesPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures/users/alice/instagram/v1"
    / "your_instagram_activity/messages/inbox/bobsmith_1234567890/message_1.json"
)
FIXTURE_DATA = FIXTURE_PATH.read_bytes()


class TestInstagramMessagesPipe(PipeTestKit):
    pipe_class = InstagramMessagesPipe
    expected_extract_count = 3   # number of records extract() yields
    expected_transform_count = 3 # number of ThreadRows run() yields

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: Path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/your_instagram_activity/messages/inbox/bob/message_1.json"
        storage.write(key, FIXTURE_DATA)
        return storage, key

    # ---- Provider-specific tests alongside the kit ----

    def test_message_directions(self, pipe_fixture):
        storage, key = pipe_fixture
        pipe = self.pipe_class()
        rows = list(pipe.run(self._make_task(key), storage))
        kinds = {r.payload["fibre_kind"] for r in rows}
        assert "SendMessage" in kinds
        assert "ReceiveMessage" in kinds
```

See [Testing](#testing) below for what the kit auto-checks.

---

## Architecture Overview

```
Pipe (ET)                          Loader (L)
┌──────────────────────────┐       ┌──────────────────────┐
│ extract(): parse archive │──────▶│ DbLoader: INSERT     │
│ transform(): → ThreadRow │       │ CheckpointLoader: GCS│
└──────────────────────────┘       └──────────────────────┘
        yields Iterator[ThreadRow]
```

- **Pipe is ET, not ETL.** Load is a separate concern that varies by deployment.
- **One Pipe class = one interaction type.** Each subclass handles one kind of data (e.g. stories, reels, DMs).
- **`Pipe.run()` yields `Iterator[ThreadRow]`.** Memory-bounded: the Loader consumes lazily.

---

## Glob Patterns (`archive_path_pattern`)

The `archive_path_pattern` ClassVar uses Python's `fnmatch` syntax to match files inside the extracted archive.

### Exact match (no wildcards)

```python
archive_path_pattern = "conversations.json"
```

Matches exactly one file → one `EtlTask` → one `extract()` call.

### Wildcard match (fan-out)

```python
archive_path_pattern = "your_instagram_activity/messages/inbox/*/message_1.json"
```

Matches multiple files (one per conversation directory). `discover_tasks()` creates **one EtlTask per matched file**, so each pipe invocation processes a single file via `task.source_uri`.

### How discovery works

In `registry.py`, `ProviderConfig.discover_tasks()` prepends the `archive_id` as a prefix:

```python
pattern = f"{archive_id}/{pipe_cls.archive_path_pattern}"
for f in files:
    if fnmatch.fnmatch(f, pattern):
        tasks.append(EtlTask(..., source_uri=f))
```

This means your `archive_path_pattern` is the path **relative to the archive root**, not including the archive ID prefix.

---

## Testing

### PipeTestKit

`PipeTestKit` (in `context_use/testing/pipe_test_kit.py`, exported from `context_use.testing`) auto-generates structural conformance tests. You subclass it and provide three things:

| Attribute | Type | Description |
|-----------|------|-------------|
| `pipe_class` | `type[Pipe]` | The pipe subclass under test |
| `expected_extract_count` | `int` | How many records `extract()` should yield from the fixture |
| `expected_transform_count` | `int` | How many `ThreadRow`s `run()` should yield |

Plus a `pipe_fixture` pytest fixture returning `(StorageBackend, key)`.

### Auto-generated tests (inherited)

The kit provides these tests automatically — you don't write them:

**Extract phase:**
- `test_extract_yields_record_schema_instances` — every yielded record is an instance of `pipe_class.record_schema`
- `test_extract_count` — total records == `expected_extract_count`

**Transform phase (via `run()`):**
- `test_run_yields_well_formed_thread_rows` — validates every `ThreadRow`:
  - `unique_key` starts with `{interaction_type}:`
  - `provider` and `interaction_type` match the pipe's ClassVars
  - `version` and `asat` are set
  - `payload` is a dict containing `fibre_kind`
  - `preview` is non-empty
- `test_run_count` — total rows == `expected_transform_count`
- `test_unique_keys_are_unique` — no duplicate `unique_key` values

**Counts:**
- `test_counts_tracked` — `pipe.extracted_count` and `pipe.transformed_count` match expected values after full iteration

**Class vars:**
- `test_class_vars_set` — all five required ClassVars (`provider`, `interaction_type`, `archive_version`, `archive_path_pattern`, `record_schema`) are set

### Provider-specific tests

Add additional test methods alongside the kit subclass for behavior unique to your pipe. Common examples:

- Message direction tests (`SendMessage` vs `ReceiveMessage`)
- Asset URI population (`row.asset_uri` is set for media pipes)
- Edge-case filtering (system messages skipped, empty content skipped)
- Specific payload structure (`fibre_kind`, nested object types)

### Helper: `_make_task(key)`

`PipeTestKit` provides `_make_task(key)` which builds a transient `EtlTask` from the pipe's ClassVars. Use it in provider-specific tests:

```python
def test_something(self, pipe_fixture):
    storage, key = pipe_fixture
    pipe = self.pipe_class()
    task = self._make_task(key)
    rows = list(pipe.run(task, storage))
    # assert ...
```

---

## Extending Payload Models

Payload models live in `context_use/etl/payload/models.py`. They follow [ActivityStreams 2.0](https://www.w3.org/TR/activitystreams-core/) conventions.

### Existing fibre types

| Fibre class | `fibre_kind` | Use case |
|-------------|-------------|----------|
| `FibreSendMessage` | `SendMessage` | User-sent messages (DMs, chat) |
| `FibreReceiveMessage` | `ReceiveMessage` | Messages received by the user |
| `FibreCreateObject` | `Create` | Media creation (stories, reels, posts) |
| `FibreTextMessage` | `TextMessage` | Text note (used as `object` in Send/Receive) |
| `FibreImage` | `Image` | Image object |
| `FibreVideo` | `Video` | Video object |
| `FibreCollection` | `Collection` | Grouping / album |

Most new pipes will use existing fibre types. **Check this table before creating a new one.**

### Adding a new fibre type

If you genuinely need a new kind:

1. **Choose the base class.** If it's an activity (verb), extend `Activity` → then `Create`, `View`, etc. If it's an object (noun), extend `Object` → then `Note`, `Image`, etc.

2. **Create the fibre class** with the `_BaseFibreMixin`:

   ```python
   class FibreListenAudio(Activity, _BaseFibreMixin):
       fibreKind: Literal["ListenAudio"] = Field("ListenAudio", alias="fibre_kind")
       object: Audio  # type: ignore[reportIncompatibleVariableOverride]
   ```

3. **Implement `_get_preview()`** returning a human-readable one-liner:

   ```python
   def _get_preview(self, provider: str | None) -> str | None:
       return f"Listened to {self.object.name}"
   ```

4. **Call `model_rebuild()`** at module level (after the class definition):

   ```python
   FibreListenAudio.model_rebuild()
   ```

5. **Add to the `FibreByType` union** (the discriminated union near the bottom of the file):

   ```python
   FibreByType = Annotated[
       FibreCreateObject | ... | FibreListenAudio,
       Field(discriminator="fibreKind"),
   ]
   ```

The mixin provides `unique_key_suffix()`, `to_dict()`, and `get_preview()` for free.

---

## Registry

The provider registry lives in `context_use/etl/providers/registry.py`.

### Structure

```python
PROVIDER_REGISTRY: dict[Provider, ProviderConfig] = {
    Provider.CHATGPT: ProviderConfig(
        pipes=[ChatGPTConversationsPipe],
    ),
    Provider.INSTAGRAM: ProviderConfig(
        pipes=[InstagramStoriesPipe, InstagramReelsPipe],
    ),
}
```

### Adding a pipe to an existing provider

1. Import your pipe class at the top of `registry.py`.
2. Append it to the `pipes` list for the relevant `Provider`.

### Adding a new provider

1. Add a member to the `Provider` enum:

   ```python
   class Provider(StrEnum):
       CHATGPT = "chatgpt"
       INSTAGRAM = "instagram"
       SPOTIFY = "spotify"  # new
   ```

2. Add a `ProviderConfig` entry to `PROVIDER_REGISTRY`:

   ```python
   Provider.SPOTIFY: ProviderConfig(
       pipes=[SpotifyListeningHistoryPipe],
   ),
   ```

---

## Versioning via Inheritance

If a provider ships a new archive format, **don't edit the existing pipe**. Instead, subclass it and override `extract()`:

```python
class ChatGPTConversationsPipeV2(ChatGPTConversationsPipe):
    archive_version = "v2"
    archive_path_pattern = "conversations_v2.json"

    def extract(self, task, storage) -> Iterator[ChatGPTConversationRecord]:
        # new parsing logic for v2 format
        ...
```

`transform()` is inherited when the `record_schema` stays the same. Register both versions if archives from both formats need to be supported simultaneously.

Key distinction: `archive_version` tracks the **provider's export format** (bumps when they change their zip structure). `ThreadRow.version` tracks the **payload schema** version (`CURRENT_THREAD_PAYLOAD_VERSION`). They are independent.

---

## Storage

Pipes interact with storage via the `StorageBackend` ABC (`context_use/storage/base.py`):

- `storage.read(key) -> bytes` — read a file in full (good for small JSON files).
- `storage.open_stream(key) -> BinaryIO` — open a stream (good for large files with `ijson`).

In tests, use `DiskStorage(str(tmp_path / "store"))` backed by pytest's `tmp_path`. Write fixture data with `storage.write(key, data)`.

The `key` is the full path including the archive ID prefix, e.g. `archive/conversations.json` or `archive/your_instagram_activity/messages/inbox/bob/message_1.json`.


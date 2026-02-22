# Contributing to context-use

context-use has two main pipelines: **ETL** (extract + transform data from provider archives into normalised threads) and **Memories** (group threads, generate first-person memories via LLM, and embed them for semantic search). Both are configured in the unified provider registry.

---

## Quick Reference — Checklist

For a new pipe in an **existing** provider (e.g. adding messages to `instagram`):

| Step | File | Action |
|------|------|--------|
| 1 | `context_use/providers/<provider>/schemas.py` | Add Pydantic record model(s) |
| 2 | `context_use/providers/<provider>/<module>.py` | Create `Pipe` subclass with `extract()` + `transform()`, define `INTERACTION_CONFIG` |
| 3 | `context_use/providers/<provider>/__init__.py` | Add the new config to `PROVIDER_CONFIG.interactions` |
| 4 | `tests/fixtures/users/alice/<provider>/v1/...` | Add fixture data (real archive structure) |
| 5 | `tests/test_<provider>_<type>.py` | Subclass `PipeTestKit` + add provider-specific tests |

For a **new** provider, also:

| Step | File | Action |
|------|------|--------|
| A | `context_use/providers/<provider>/` | Create package (`__init__.py`, `schemas.py`, pipe module) |
| B | `context_use/providers/registry.py` | Add `Provider` enum member + import `PROVIDER_CONFIG` into `PROVIDER_REGISTRY` |

If the provider needs a new fibre (payload) type, see [Extending Payload Models](#extending-payload-models).

---

## Package Layout

```
context_use/
  providers/              ← unified provider configs (ETL + memory)
    types.py              ← InteractionConfig, ProviderConfig dataclasses
    registry.py           ← Provider enum, PROVIDER_REGISTRY dict, lookup functions
    chatgpt/
      __init__.py         ← assembles PROVIDER_CONFIG from interaction configs
      schemas.py          ← record models
      conversations.py    ← Pipe subclass + INTERACTION_CONFIG
    instagram/
      __init__.py         ← assembles PROVIDER_CONFIG from interaction configs
      schemas.py
      media.py            ← Pipe subclasses + STORIES_CONFIG, REELS_CONFIG
  etl/                    ← reusable ETL building blocks
    core/pipe.py          ← Pipe ABC
    core/types.py         ← ThreadRow
    core/loader.py        ← DbLoader
    payload/models.py     ← Fibre models (ActivityStreams)
    models/               ← EtlTask, Thread, Archive
  memories/               ← reusable memory building blocks
    config.py             ← MemoryConfig dataclass
    prompt/base.py        ← BasePromptBuilder ABC, GroupContext, MemorySchema
    prompt/conversation.py← ConversationMemoryPromptBuilder (stock)
    prompt/media.py       ← MediaMemoryPromptBuilder (stock)
    manager.py            ← MemoryBatchManager (framework)
    extractor.py          ← MemoryExtractor (framework)
  batch/                  ← reusable batch/grouping building blocks
    grouper.py            ← ThreadGrouper ABC, WindowGrouper, CollectionGrouper
    factory.py            ← BaseBatchFactory
    manager.py            ← BaseBatchManager
```

**Dependency rule:** `providers` imports from `etl`, `memories`, and `batch`. Those three never import from `providers`.

---

## Architecture Overview

The full pipeline for a single provider archive:

```
  ZIP archive
       │
       ▼
  ┌────────────────────────────────────────────────┐
  │  ETL Pipeline                                   │
  │                                                 │
  │  Pipe.extract()  →  Pipe.transform()  →  Load   │
  │  (parse archive)    (→ ThreadRow)      (→ DB)   │
  └────────────────────┬───────────────────────────┘
                       │
                  Thread rows in DB
                       │
                       ▼
  ┌────────────────────────────────────────────────┐
  │  Memory Pipeline                                │
  │                                                 │
  │  Grouper         →  PromptBuilder  →  LLM batch │
  │  (partition          (format           (generate │
  │   threads)            prompts)          memories)│
  │                                         │       │
  │                                         ▼       │
  │                                    Embed batch  │
  │                                    (vectorise)  │
  └────────────────────────────────────────────────┘
                       │
                  Memories + embeddings in DB
                       │
                       ▼
                  Semantic search
```

- **Pipe is ET, not ETL.** Load is a separate concern handled by `DbLoader`.
- **One Pipe class = one interaction type.** Each subclass handles one kind of data (e.g. stories, reels, DMs).
- **`Pipe.run()` yields `Iterator[ThreadRow]`.** Memory-bounded; the Loader consumes lazily.
- **`InteractionConfig` = pipe + memory config.** Declared once per interaction type, co-located with the pipe class.
- **Memory generation is async and batched.** The `MemoryBatchManager` state machine submits OpenAI batch jobs for both generation and embedding, polling until complete.

---

## Unified Registry

Configuration is split across three layers so each provider owns its own config while the framework stays clean:

| File | Responsibility |
|------|---------------|
| `providers/types.py` | `InteractionConfig` and `ProviderConfig` dataclasses (shared types) |
| `providers/<provider>/<module>.py` | `INTERACTION_CONFIG` co-located with each pipe class |
| `providers/<provider>/__init__.py` | `PROVIDER_CONFIG` assembling the provider's interaction configs |
| `providers/registry.py` | `Provider` enum, `PROVIDER_REGISTRY` dict, lookup functions |

### Types (`providers/types.py`)

```python
@dataclass
class InteractionConfig:
    """Full pipeline config for one interaction type."""
    pipe: type[Pipe]
    memory: MemoryConfig | None = None  # None = ETL-only

@dataclass
class ProviderConfig:
    interactions: list[InteractionConfig]
```

### How config flows

Each pipe module defines its `InteractionConfig` alongside the pipe class:

```python
# providers/chatgpt/conversations.py
INTERACTION_CONFIG = InteractionConfig(
    pipe=ChatGPTConversationsPipe,
    memory=MemoryConfig(
        prompt_builder=ConversationMemoryPromptBuilder,
        grouper=CollectionGrouper,
    ),
)
```

The provider `__init__.py` assembles them into a `ProviderConfig`:

```python
# providers/chatgpt/__init__.py
PROVIDER_CONFIG = ProviderConfig(interactions=[INTERACTION_CONFIG])
```

And `registry.py` collects all providers:

```python
# providers/registry.py
PROVIDER_REGISTRY: dict[Provider, ProviderConfig] = {
    Provider.CHATGPT: _CHATGPT_CONFIG,
    Provider.INSTAGRAM: _INSTAGRAM_CONFIG,
}
```

### Adding a pipe to an existing provider

1. In the pipe module, define `INTERACTION_CONFIG` with the pipe class and its `MemoryConfig`.
2. In the provider's `__init__.py`, import it and add it to the `PROVIDER_CONFIG.interactions` list.

No changes to `registry.py` needed.

### Adding a new provider

1. Create the provider package under `context_use/providers/<provider>/`:

   - `schemas.py` — Pydantic record model(s)
   - One or more pipe modules (e.g. `history.py`) — each with its `INTERACTION_CONFIG`
   - `__init__.py` — assemble `PROVIDER_CONFIG`:

     ```python
     from context_use.providers.spotify.history import (
         INTERACTION_CONFIG as _HISTORY_CONFIG,
         SpotifyListeningHistoryPipe,
     )
     from context_use.providers.spotify.schemas import SpotifyListenRecord
     from context_use.providers.types import ProviderConfig

     PROVIDER_CONFIG = ProviderConfig(interactions=[_HISTORY_CONFIG])

     __all__ = [
         "SpotifyListenRecord",
         "SpotifyListeningHistoryPipe",
         "PROVIDER_CONFIG",
     ]
     ```

2. Add a member to the `Provider` enum in `registry.py`:

   ```python
   class Provider(StrEnum):
       CHATGPT = "chatgpt"
       INSTAGRAM = "instagram"
       SPOTIFY = "spotify"  # new
   ```

3. Import and add the provider config to `PROVIDER_REGISTRY`:

   ```python
   from context_use.providers.spotify import PROVIDER_CONFIG as _SPOTIFY_CONFIG

   PROVIDER_REGISTRY: dict[Provider, ProviderConfig] = {
       ...
       Provider.SPOTIFY: _SPOTIFY_CONFIG,
   }
   ```

---

## Worked Example — Instagram Messages Pipe

This walkthrough adds an `InstagramMessagesPipe` that processes Instagram DM conversations from files matching `your_instagram_activity/messages/inbox/*/message_1.json`.

### Step 1: Define the Record Schema

The record schema is the Pydantic model that `extract()` yields. It represents one parsed item from the archive — here, one chat message.

Create or extend `context_use/providers/instagram/schemas.py`:

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

Create `context_use/providers/instagram/messages.py`:

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
from context_use.providers.instagram.schemas import InstagramDirectMessage
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
        published = datetime.fromtimestamp(record.timestamp_ms / 1000.0, tz=UTC)

        context = Collection(
            name=record.thread_title,
            id=record.thread_path,
        )
        message = FibreTextMessage(content=record.content, context=context)

        # Determine direction: messages from the archive owner are sent,
        # everything else is received.
        if record.sender_name == "alice_synthetic":
            target = Application(name=record.thread_title)
            payload = FibreSendMessage(
                object=message, target=target, published=published,
            )
        else:
            actor = Application(name=record.sender_name)
            payload = FibreReceiveMessage(
                object=message, actor=actor, published=published,
            )

        return ThreadRow(
            unique_key=f"{self.interaction_type}:{payload.unique_key_suffix()}",
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview("Instagram") or "",
            payload=payload.to_dict(),
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=published,
            source=record.source,
        )
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
- Return a `ThreadRow` with **all required fields**:

| Field | How to set it |
|-------|---------------|
| `unique_key` | `f"{self.interaction_type}:{payload.unique_key_suffix()}"` |
| `provider` | `self.provider` |
| `interaction_type` | `self.interaction_type` |
| `preview` | `payload.get_preview(provider)` — human-readable one-liner |
| `payload` | `payload.to_dict()` |
| `version` | `CURRENT_THREAD_PAYLOAD_VERSION` |
| `asat` | The record's timestamp as a timezone-aware `datetime` |

Optional fields:

| Field | When to set it |
|-------|----------------|
| `source` | `record.source` — raw JSON for audit/debug (set whenever the record carries a `source` field) |
| `asset_uri` | `f"{task.archive_id}/{record.uri}"` — set for media pipes so the Loader can locate the binary asset in storage |

#### `run()` — Do Not Override

`run()` is a template method on the base class. It calls `extract()`, then `transform()` for each record, tracks `extracted_count` / `transformed_count`, and yields `ThreadRow` instances lazily. Do not override it.

### Step 3: Register the Pipe with Memory Config

Add an `INTERACTION_CONFIG` at the bottom of `context_use/providers/instagram/messages.py` (same file as the pipe):

```python
from context_use.batch.grouper import CollectionGrouper
from context_use.memories.config import MemoryConfig
from context_use.memories.prompt.conversation import ConversationMemoryPromptBuilder
from context_use.providers.types import InteractionConfig

INTERACTION_CONFIG = InteractionConfig(
    pipe=InstagramMessagesPipe,
    memory=MemoryConfig(
        prompt_builder=ConversationMemoryPromptBuilder,
        grouper=CollectionGrouper,
    ),
)
```

Then add it to the provider's `__init__.py`:

```python
# context_use/providers/instagram/__init__.py
from context_use.providers.instagram.messages import (
    INTERACTION_CONFIG as _MESSAGES_CONFIG,
)

PROVIDER_CONFIG = ProviderConfig(
    interactions=[_STORIES_CONFIG, _REELS_CONFIG, _MESSAGES_CONFIG]
)
```

Each `InteractionConfig` declares both the ETL pipe and the memory generation strategy in one place. Set `memory=None` for ETL-only interaction types that don't generate memories. No changes to `registry.py` needed when adding to an existing provider.

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

from context_use.providers.instagram.messages import InstagramMessagesPipe
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

## Memory Pipeline

After ETL loads threads into the database, the memory pipeline groups them, sends prompts to an LLM for memory extraction, and embeds the resulting memories for semantic search.

### How It Works

1. **Group threads.** A `ThreadGrouper` partitions threads into atomic groups (by conversation, by time window, etc.). Each group becomes one LLM prompt.

2. **Build prompts.** A `BasePromptBuilder` formats each group's threads into a `PromptItem` — the text prompt plus any image/video assets and a JSON response schema.

3. **Submit to LLM.** The `MemoryExtractor` wraps `LLMClient.batch_submit()` to send all prompts as an OpenAI batch job. The LLM returns structured `MemorySchema` responses (a list of memories with dates).

4. **Store memories.** Parsed memories are written to the `tapestry_memories` table.

5. **Embed memories.** A second batch job embeds each memory's text. The resulting vectors are stored alongside the memory rows for semantic search.

### MemoryBatchManager State Machine

`MemoryBatchManager` (`context_use/memories/manager.py`) orchestrates steps 1–5 as an async state machine:

```
CREATED
  → MEMORY_GENERATE_PENDING   (batch job submitted)
  → MEMORY_GENERATE_COMPLETE   (memories stored in DB)
  → MEMORY_EMBED_PENDING       (embedding batch submitted)
  → MEMORY_EMBED_COMPLETE      (embeddings stored on memory rows)
  → COMPLETE

At any point → SKIPPED (no content) or FAILED (error).
```

Each transition is driven by `_transition()`, which the `BaseBatchManager` polling loop calls repeatedly. Pending states return themselves with an incremented poll count until results arrive.

### MemoryConfig

`MemoryConfig` (`context_use/memories/config.py`) declares how threads from a given interaction type are grouped and turned into memories:

```python
@dataclass(frozen=True)
class MemoryConfig:
    prompt_builder: type[BasePromptBuilder]  # how to build LLM prompts
    grouper: type[ThreadGrouper]             # how to group threads
    prompt_builder_kwargs: dict[str, Any]    # extra args for prompt builder
    grouper_kwargs: dict[str, Any]           # extra args for grouper
```

It provides two factory methods:
- `create_prompt_builder(contexts)` — instantiate the prompt builder with the given `GroupContext` list.
- `create_grouper()` — instantiate the grouper with any configured kwargs.

### Groupers

Groupers partition threads into `ThreadGroup` objects. Each group becomes one LLM prompt.

#### `ThreadGrouper` ABC

```python
class ThreadGrouper(ABC):
    @abstractmethod
    def group(self, threads: list[Thread]) -> list[ThreadGroup]:
        """Partition threads into groups that must be processed together."""
        ...
```

#### Stock groupers

| Grouper | Module | Group key | Use case |
|---------|--------|-----------|----------|
| `WindowGrouper` | `batch.grouper` | `"{from_date}/{to_date}"` | Sliding time-window; good for media (stories, reels) |
| `CollectionGrouper` | `batch.grouper` | Collection ID from payload | Group by conversation / thread ID; good for chats |

**`WindowGrouper`** splits threads into overlapping time windows controlled by `WindowConfig`:

```python
@dataclass(frozen=True)
class WindowConfig:
    window_days: int = 5       # width of each window
    overlap_days: int = 1      # overlap between consecutive windows
    max_memories: int | None   # per-window cap (None = auto-scale)
    min_memories: int | None   # per-window floor (None = auto-scale)
```

**`CollectionGrouper`** reads the collection ID from each thread's payload (via `thread.get_collection()`) and buckets threads by that ID. Threads with no collection are dropped.

#### Writing a custom grouper

If neither stock grouper fits, subclass `ThreadGrouper`:

```python
from context_use.batch.grouper import ThreadGrouper, ThreadGroup

class DailyGrouper(ThreadGrouper):
    """One group per calendar day."""

    def group(self, threads: list[Thread]) -> list[ThreadGroup]:
        from collections import defaultdict
        by_day: dict[str, list[Thread]] = defaultdict(list)
        for t in threads:
            by_day[t.asat.date().isoformat()].append(t)
        return [
            ThreadGroup(threads=sorted(ts, key=lambda t: t.asat))
            for day, ts in sorted(by_day.items())
        ]
```

Reference it in the registry:

```python
InteractionConfig(
    pipe=SomePipe,
    memory=MemoryConfig(
        prompt_builder=SomePromptBuilder,
        grouper=DailyGrouper,
    ),
)
```

### Prompt Builders

Prompt builders turn grouped threads into `PromptItem` objects ready for the LLM.

#### `BasePromptBuilder` ABC

```python
class BasePromptBuilder(ABC):
    def __init__(self, contexts: list[GroupContext]) -> None:
        self.contexts = contexts

    @abstractmethod
    def build(self) -> list[PromptItem]:
        """Return one PromptItem per processable group."""
        ...

    @abstractmethod
    def has_content(self) -> bool:
        """Return True if there is anything worth sending to the LLM."""
        ...
```

The base class also provides `_format_context(ctx)` which builds an optional preamble from prior memories and recent threads (for delta / incremental runs).

#### `GroupContext`

Each group is represented as a `GroupContext` passed to the prompt builder:

| Field | Type | Description |
|-------|------|-------------|
| `group_id` | `str` | UUID identifying this group instance |
| `new_threads` | `list[Thread]` | Threads to generate memories from |
| `prior_memories` | `list[str]` | Previously extracted memory texts (for delta context) |
| `recent_threads` | `list[Thread]` | Recent threads already processed (for continuity) |

#### `MemorySchema`

The LLM response schema that all prompt builders use:

```python
class MemorySchema(BaseModel):
    memories: list[Memory]

class Memory(BaseModel):
    content: str       # 1-2 sentence first-person memory
    from_date: str     # YYYY-MM-DD
    to_date: str       # YYYY-MM-DD
```

#### `PromptItem`

What `build()` returns — one per group:

| Field | Type | Description |
|-------|------|-------------|
| `item_id` | `str` | Group key (used as `custom_id` in the OpenAI batch) |
| `prompt` | `str` | The formatted text prompt |
| `response_schema` | `dict` | `MemorySchema.json_schema()` |
| `asset_paths` | `list[str]` | Local file paths for images/videos (media prompts only) |

#### Stock prompt builders

| Builder | Module | Use case |
|---------|--------|----------|
| `ConversationMemoryPromptBuilder` | `memories.prompt.conversation` | Chat / DM transcripts with `[USER]` and `[ASSISTANT]` labels |
| `MediaMemoryPromptBuilder` | `memories.prompt.media` | Visual media grouped by day, with image references |

**`ConversationMemoryPromptBuilder`** formats threads as a timestamped transcript, instructs the LLM to extract the user's experience (what they worked on, decided, learned), and scales the max memory count with conversation length.

**`MediaMemoryPromptBuilder`** groups posts by day, labels images as `[Image N]`, and instructs the LLM to study every image carefully — reading signs, screens, logos, and connecting posts across days.

#### Writing a custom prompt builder

If the stock builders don't fit, subclass `BasePromptBuilder` (or one of the stock builders):

```python
# context_use/providers/slack/prompt.py
from context_use.memories.prompt.conversation import ConversationMemoryPromptBuilder

class SlackMemoryPromptBuilder(ConversationMemoryPromptBuilder):
    """Slack-specific: includes channel name, skips bot messages."""

    def _format_transcript(self, threads):
        lines = []
        for t in sorted(threads, key=lambda t: t.asat):
            if t.preview.startswith("[BOT]"):
                continue
            role = "USER" if not t.is_inbound else "OTHER"
            ts = t.asat.strftime("%Y-%m-%d %H:%M")
            content = t.get_message_content() or ""
            lines.append(f"[{role} {ts}] {content}")
        return "## Transcript\n\n" + "\n".join(lines)
```

Then reference it in the registry:

```python
InteractionConfig(
    pipe=SlackMessagesPipe,
    memory=MemoryConfig(
        prompt_builder=SlackMemoryPromptBuilder,
        grouper=CollectionGrouper,
    ),
)
```

### Reusable combinations

Most providers can compose `MemoryConfig` from stock components:

| Interaction pattern | Grouper | Prompt builder |
|---------------------|---------|----------------|
| Chat / DM conversations | `CollectionGrouper` | `ConversationMemoryPromptBuilder` |
| Visual media (stories, reels, posts) | `WindowGrouper` | `MediaMemoryPromptBuilder` |

---

## ETL Pipe Reference

### Glob Patterns (`archive_path_pattern`)

The `archive_path_pattern` ClassVar uses Python's `fnmatch` syntax to match files inside the extracted archive.

#### Exact match (no wildcards)

```python
archive_path_pattern = "conversations.json"
```

Matches exactly one file → one `EtlTask` → one `extract()` call.

#### Wildcard match (fan-out)

```python
archive_path_pattern = "your_instagram_activity/messages/inbox/*/message_1.json"
```

Matches multiple files (one per conversation directory). `discover_tasks()` creates **one EtlTask per matched file**, so each pipe invocation processes a single file via `task.source_uri`.

#### How discovery works

In `registry.py`, `ProviderConfig.discover_tasks()` prepends the `archive_id` as a prefix:

```python
pattern = f"{archive_id}/{pipe_cls.archive_path_pattern}"
for f in files:
    if fnmatch.fnmatch(f, pattern):
        tasks.append(EtlTask(..., source_uri=f))
```

This means your `archive_path_pattern` is the path **relative to the archive root**, not including the archive ID prefix.

### ThreadRow Reference

`ThreadRow` (`context_use.etl.core.types`) is the plain value object that flows from `Pipe.transform()` to the Loader:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `unique_key` | `str` | ✓ | Globally unique key, formatted as `{interaction_type}:{hash}` |
| `provider` | `str` | ✓ | Provider identifier — must match `Pipe.provider` |
| `interaction_type` | `str` | ✓ | Interaction type — must match `Pipe.interaction_type` |
| `preview` | `str` | ✓ | Human-readable one-liner (shown in search results) |
| `payload` | `dict` | ✓ | ActivityStreams payload dict (from `fibre.to_dict()`) — must contain `fibre_kind` |
| `version` | `str` | ✓ | Payload schema version — use `CURRENT_THREAD_PAYLOAD_VERSION` |
| `asat` | `datetime` | ✓ | Timezone-aware timestamp of the original interaction |
| `source` | `str \| None` | | Raw JSON of the original record, for audit/debug |
| `asset_uri` | `str \| None` | | Storage key for an associated binary asset (image, video) |

Infrastructure fields (`id`, `etl_task_id`, timestamps) are added by the Loader when persisting — pipes never set them.

### EtlTask Reference

`EtlTask` (`context_use.etl.models.etl_task`) is passed to both `extract()` and `transform()`. Fields most relevant to pipe authors:

| Field | Type | Description |
|-------|------|-------------|
| `source_uri` | `str` | Storage key for the archive file to read (e.g. `archive/conversations.json`) |
| `archive_id` | `str` | Archive identifier — used to construct `asset_uri` for media pipes |
| `provider` | `str` | Provider identifier (same as `Pipe.provider`) |
| `interaction_type` | `str` | Interaction type (same as `Pipe.interaction_type`) |

Other fields (`id`, `status`, `extracted_count`, `transformed_count`, `uploaded_count`) are managed by the framework and Loader.

### Extending Payload Models

Payload models live in `context_use/etl/payload/models.py`. They follow [ActivityStreams 2.0](https://www.w3.org/TR/activitystreams-core/) conventions.

#### Existing fibre types

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

#### Adding a new fibre type

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

The mixin provides these methods for free:

- `unique_key_suffix()` — deterministic SHA-256 hash of the serialised payload (first 16 hex chars).
- `to_dict()` — serialise to a plain dict (via `model_dump_json`, excluding `None` values, using aliases).
- `get_preview(provider)` — delegates to `_get_preview()`; catches exceptions and returns `None` on error.
- `get_asat()` — extracts the `published` datetime from the payload, if set.

### Versioning via Inheritance

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

### Shared Base Class Pattern

When a provider has multiple interaction types that share the same `record_schema` and `transform()` logic, extract the shared code into a private base class. Only the concrete subclasses (which set `interaction_type` and `archive_path_pattern`) get registered.

The Instagram media pipes use this pattern:

```python
class _InstagramMediaPipe(Pipe[InstagramMediaRecord]):
    """Shared transform logic for stories and reels."""

    provider = "instagram"
    archive_version = "v1"
    record_schema = InstagramMediaRecord

    def transform(self, record, task) -> ThreadRow:
        # shared payload-building logic ...


class InstagramStoriesPipe(_InstagramMediaPipe):
    interaction_type = "instagram_stories"
    archive_path_pattern = "your_instagram_activity/media/stories.json"

    def extract(self, task, storage) -> Iterator[InstagramMediaRecord]:
        # stories-specific parsing ...


class InstagramReelsPipe(_InstagramMediaPipe):
    interaction_type = "instagram_reels"
    archive_path_pattern = "your_instagram_activity/media/reels.json"

    def extract(self, task, storage) -> Iterator[InstagramMediaRecord]:
        # reels-specific parsing ...
```

Only `InstagramStoriesPipe` and `InstagramReelsPipe` are registered in `PROVIDER_REGISTRY`; the private base class is not.

### Storage

Pipes interact with storage via the `StorageBackend` ABC (`context_use/storage/base.py`):

- `storage.read(key) -> bytes` — read a file in full (good for small JSON files).
- `storage.open_stream(key) -> BinaryIO` — open a stream (good for large files with `ijson`).

In tests, use `DiskStorage(str(tmp_path / "store"))` backed by pytest's `tmp_path`. Write fixture data with `storage.write(key, data)`.

The `key` is the full path including the archive ID prefix, e.g. `archive/conversations.json` or `archive/your_instagram_activity/messages/inbox/bob/message_1.json`.

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

---
name: context-use
description: "You MUST use this to search the user's personal memories before responding to anything personal. Personal memory from real data exports (ChatGPT, Claude, Instagram, Google). Use `context-use` to search and manage memories extracted from the user's data. Use this skill whenever the user references past conversations, personal history, people, places, projects, habits, or events — even if they don't mention 'memories' explicitly."
---

# context-use — Personal Memory

Use the `context-use` CLI to search the user's personal memories.
Install: `pip install context-use`
Memories are stored in a local SQLite database, searchable via semantic search.

**OpenAI API key required** for memory generation and search. Run `context-use config show` to check. If not set, ask the user for their key and run `context-use config set-key <key>`.

## Workflow

1. **Before responding to anything personal:** Run `context-use memories search` to find relevant context.
2. **After ingesting new data:** Run `context-use agent synthesise` to create pattern memories.

## Commands

### 1. Search Memories

**Overview:** Semantic search across the user's personal memories. Returns the most relevant memories ranked by similarity.

**Use this skill when:**
- The user references past conversations, projects, people, or events
- They say "remember when...", "we talked about...", "last time..."
- A topic comes up where their personal history would add useful context
- You need to recall something about the user's life, habits, or preferences

**Do NOT use this skill when:**
- The question is purely technical with no personal angle
- The information is general knowledge, not personal history
- You already searched for the same topic earlier in this session

```bash
context-use memories search "relevant query" --top-k 5
```

With date filters:

```bash
context-use memories search "query" --from 2024-01-01 --to 2024-12-31
```

Weave results into your response naturally — don't announce "I found this in your memories", just use the context like a friend who knows them would. If nothing relevant comes back, move on without mentioning it.

### 2. List & Browse Memories

**Overview:** Browse all memories, grouped by month.

```bash
context-use memories list
context-use memories list --limit 20
```

Full details on a specific memory:

```bash
context-use memories get <uuid>
```

### 3. Manage Memories

**Overview:** Create, edit, or archive memories when the user asks.

**Use this skill when:**
- The user wants to record something ("remember that I...")
- A memory needs correction
- Memories should be merged or superseded

**Do NOT use this skill when:**
- The information is transient or only relevant to the current task

```bash
context-use memories create --content "..." --from 2024-03-01 --to 2024-03-31
context-use memories update <id> --content "..."
context-use memories archive <id1> <id2> --superseded-by <new-id>
```

### 4. Export Memories

```bash
context-use memories export                        # Markdown (default)
context-use memories export --format json          # JSON
context-use memories export --out path/to/file.md  # Custom path
```

### 5. Agent Commands

**Overview:** Built-in agent for complex memory tasks.

```bash
context-use agent synthesise    # Distill pattern memories from events
context-use agent profile       # Compile a first-person user profile
context-use agent ask "..."     # Free-form memory task
```

Suggest `synthesise` after ingesting new data — it creates higher-level pattern memories that make future searches more useful.

### 6. Ingest Data Exports

**Overview:** Process a ZIP export from a supported provider into searchable memories.

The user needs to download their export themselves (requires their personal login):

| Provider | How to export |
|----------|---------------|
| ChatGPT | chatgpt.com → Settings → Data Controls → Export Data |
| Claude | claude.ai → Settings → Account → Export Data |
| Instagram | App → Settings → Accounts Center → Download your information (select **JSON** format) |
| Google | takeout.google.com → select products → export as ZIP |

Tell them not to unzip it. Once they provide the path:

```bash
context-use pipeline --quick <provider> <path-to-zip>
```

Where `<provider>` is `chatgpt`, `claude`, `instagram`, or `google`.

Use `--quick` for a fast preview (last 30 days). For full history:

```bash
context-use pipeline <provider> <path-to-zip>
```

Verify it worked:

```bash
context-use memories list --limit 5
```

## Error Handling

**User Action Required:**
Show these to the user when they occur.

| Error | Fix |
|-------|-----|
| "OpenAI API key not configured" | Ask the user for their key, then `context-use config set-key <key>` |
| Rate limits in quick mode | Switch to batch: `context-use pipeline <provider> <zip>` (without `--quick`) |
| Export not ready / taking hours | Normal for Instagram and Google — user needs to wait |

**Agent-Fixable Errors:**
Handle these yourself and retry.

| Error | Fix |
|-------|-----|
| `context-use` not found | `pip install context-use` (or `uv tool install context-use`) |
| No memories found | User hasn't ingested yet — guide them through [Ingest Data Exports](#6-ingest-data-exports) |
| Unknown provider | Use one of: `chatgpt`, `claude`, `instagram`, `google` |
| File not found | Verify path with `ls`, ask user to confirm the ZIP location |

### Quick Diagnosis

```bash
context-use config show
```

Shows API key status, model, database path, and data directory.

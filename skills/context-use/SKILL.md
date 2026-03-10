---
name: context-use
description: >
  Personal memory from real data exports. Uses the context-use CLI
  to search and manage the user's memories extracted from ChatGPT,
  Claude, Instagram, and Google exports.
user-invocable: true
---

# context-use — Personal Memory

You have access to the user's personal memories via the `context-use` CLI.
These are real memories extracted from their data exports (ChatGPT, Claude,
Instagram, Google) — not LLM-generated summaries.

Use these memories to personalise your responses. When a topic comes up
that the user's memories might cover, search for relevant context before
answering.

## Preflight — run once per session

Before first use in a session, check readiness:

```bash
context-use --version
```

- **Command not found** → go to [First-Time Setup](#first-time-setup).
- **Command works** → check if memories exist:

```bash
context-use memories list --limit 1
```

- **No memories found** → the user has installed but hasn't run the pipeline yet. Ask if they have a data export ready and guide them through [Running the Pipeline](#running-the-pipeline).
- **Memories returned** → ready. Proceed to [Using Memories](#using-memories).

## Using Memories

### Search for relevant context

When the user asks about a topic, search their memories for relevant context:

```bash
context-use memories search "the topic or question" --top-k 5
```

Narrow by date range when appropriate:

```bash
context-use memories search "query" --from 2024-01-01 --to 2024-12-31
```

Use what you find to inform your response — reference specifics (names,
places, dates) from the memories rather than making generic statements.
If the search returns nothing relevant, don't mention it — just respond
normally.

### Browse memories

```bash
context-use memories list                    # all, grouped by month
context-use memories list --limit 20         # recent subset
```

### Get full details on a specific memory

```bash
context-use memories get <memory-uuid>
```

### Export

```bash
context-use memories export                        # Markdown
context-use memories export --format json          # JSON
context-use memories export --out path/to/file.md  # custom path
```

### Manage memories

```bash
# Create a new memory
context-use memories create --content "..." --from 2024-03-01 --to 2024-03-31

# Edit an existing memory
context-use memories update <id> --content "..." --from ... --to ...

# Archive superseded memories
context-use memories archive <id1> <id2> --superseded-by <new-id>
```

### Personal agent

For complex memory tasks, use the built-in agent:

```bash
context-use agent synthesise    # create higher-level pattern memories
context-use agent profile       # compile a first-person user profile
context-use agent ask "..."     # free-form memory task
```

## First-Time Setup

Walk the user through these steps. Only proceed when each step succeeds.

### 1. Install

```bash
pip install context-use
```

Or with uv:

```bash
uv tool install context-use
```

Verify: `context-use --version`

### 2. Set up OpenAI API key

Needed for memory generation and semantic search.

```bash
context-use config set-key
```

Or via environment variable: `export OPENAI_API_KEY=sk-...`

If the user doesn't have an API key, direct them to
https://platform.openai.com/api-keys.

### 3. Download a data export

The user needs a ZIP export from one of the supported providers. Guide them
based on which provider they use:

| Provider | Steps |
|----------|-------|
| ChatGPT | https://chatgpt.com → Settings → Data Controls → Export Data. Download link arrives by email. |
| Claude | https://claude.ai → Settings → Account → Export Data. Download link arrives by email. |
| Instagram | Instagram app → Settings → Accounts Center → Your information and permissions → Download your information. Select **JSON** format (not HTML), "All time". Notification when ready. |
| Google | https://takeout.google.com → select products → export as ZIP. |

Tell the user: **do not extract the ZIP**. The CLI reads it directly.

### 4. Run the pipeline

See [Running the Pipeline](#running-the-pipeline).

## Running the Pipeline

For a quick preview (real-time API, last 30 days):

```bash
context-use pipeline --quick path/to/export.zip
```

For the full export (batch API, cheaper, all history):

```bash
context-use pipeline chatgpt path/to/export.zip
```

Replace `chatgpt` with the provider name: `chatgpt`, `claude`,
`instagram`, or `google`.

After the pipeline completes, verify:

```bash
context-use memories list --limit 5
```

## Configuration

```bash
context-use config show    # show all settings and their sources
context-use config path    # print config file location
```

Config file: `~/.config/context-use/config.toml`

| Setting | Env var | Default |
|---------|---------|---------|
| API key | `OPENAI_API_KEY` | — |
| Model | `OPENAI_MODEL` | `gpt-5.2` |
| Embedding model | `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-large` |
| Database | `CONTEXT_USE_DB_PATH` | `context_use.db` |

## Error Handling

- **context-use not found** → guide [First-Time Setup](#first-time-setup).
- **No API key** → `context-use config set-key` or `export OPENAI_API_KEY=...`.
- **No memories** → user needs to run the pipeline first.
- **Rate limits in quick mode** → switch to batch: `context-use pipeline` (without `--quick`).
- **Export not ready** → normal, exports from Instagram/Google can take hours. User just needs to wait.

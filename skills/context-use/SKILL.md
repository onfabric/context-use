---
name: context-use
description: >
  Triggered when the user wants to turn data exports into AI memory —
  ingesting archives, generating memories, searching, exporting,
  or running the personal memory agent via the context-use CLI.
user-invocable: true
---

# context-use

Turn data exports from ChatGPT, Claude, Instagram, and other platforms
into portable, searchable AI memory using the `context-use` CLI.

## When to Use

Use this skill when the user wants to:

- Ingest a data export archive (ZIP) from a supported provider.
- Generate memories from ingested data.
- Search, list, export, or manage their memories.
- Run the personal memory agent (synthesise patterns, compile a profile, ask questions).
- Configure the tool (API key, model, paths).

## Required Inputs

1. **Data export** — a ZIP file from a supported provider, placed in `context-use-data/input/` or referenced by path.
2. **OpenAI API key** — required for memory generation, semantic search, and the agent. Not needed for ingest, listing, or export.

## Supported Providers

| Provider | Status | Data types |
|----------|--------|------------|
| ChatGPT | Available | Conversations |
| Claude | Available | Conversations |
| Instagram | Available | Stories, Reels, Posts, Likes, Followers, Comments, Saved, Connections, Views, Searches |
| Google | Available | Searches, YouTube, Shopping, Discover, Lens |

## Step-by-Step Workflow

### 1. Install

```bash
pip install context-use
# or
uv tool install context-use
```

### 2. Configure the API key

```bash
context-use config set-key <OPENAI_API_KEY>
```

Or set via environment variable:

```bash
export OPENAI_API_KEY=sk-...
```

Or run any API-requiring command and follow the interactive prompt.

### 3. Prepare the data export

Download the ZIP export from the provider (see provider-specific export guides). Either:

- Place it in `context-use-data/input/` and use interactive mode, or
- Pass the path directly to the CLI.

### 4. Run the pipeline

#### Quick mode (real-time API, last 30 days, fast preview)

```bash
context-use pipeline --quick path/to/export.zip
```

Provider is auto-detected from the filename or selected interactively.
Override the time window with `--last-days`:

```bash
context-use pipeline --quick --last-days 90 path/to/export.zip
```

Quick mode exports results to `context-use-data/output/` as Markdown and JSON.

#### Full pipeline (batch API, all history, cheaper)

```bash
context-use pipeline                              # interactive archive picker
context-use pipeline chatgpt path/to/export.zip   # direct
context-use pipeline --last-days 60               # limit history
```

Uses OpenAI's batch API. Typical runtime: 2–10 minutes.

#### Step-by-step alternative

```bash
context-use ingest chatgpt path/to/export.zip     # step 1: parse archive (no API key needed)
context-use memories generate                      # step 2: generate memories (batch API)
```

### 5. Explore memories

```bash
context-use memories list                          # browse all memories
context-use memories list --limit 20               # show only 20
context-use memories search "hiking trips"         # semantic search
context-use memories search --from 2024-01-01 --to 2024-06-30 --top-k 5
context-use memories get <memory-uuid>             # full detail of one memory
context-use memories export                        # export to Markdown (default)
context-use memories export --format json          # export to JSON
context-use memories export --out my-memories.md   # custom output path
```

### 6. Manage memories

```bash
context-use memories create --content "I started learning piano in March" \
  --from 2024-03-01 --to 2024-03-31

context-use memories update <id> --content "Updated text" --from 2024-03-01 --to 2024-04-30

context-use memories archive <id1> <id2> --superseded-by <new-id>
```

### 7. Personal memory agent

```bash
context-use agent synthesise                       # synthesise pattern memories from event memories
context-use agent profile                          # compile a first-person user profile
context-use agent ask "What topics keep coming back across all my conversations?"
```

The agent has read/write access to the memory store. It can search, create,
update, and archive memories. The `synthesise` command runs topic-by-topic
deep dives and creates higher-level pattern memories. The `profile` command
is read-only and outputs a Markdown profile to stdout.

### 8. Configuration

```bash
context-use config show                            # show all settings and sources
context-use config set-key                         # change API key interactively
context-use config set-key sk-...                  # set key directly
context-use config path                            # print config file location
```

Config file: `~/.config/context-use/config.toml`

| Setting | TOML key | Env var | Default |
|---------|----------|---------|---------|
| OpenAI API key | `[openai] api_key` | `OPENAI_API_KEY` | — |
| LLM model | `[openai] model` | `OPENAI_MODEL` | `gpt-5.2` |
| Embedding model | `[openai] embedding_model` | `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-large` |
| Database path | `[store] path` | `CONTEXT_USE_DB_PATH` | `context_use.db` |
| Data directory | `[data] dir` | — | `./context-use-data` |

### 9. Reset

```bash
context-use reset          # wipes all data, asks for confirmation
context-use reset --yes    # skip confirmation
```

## Output Format

- **Memories list**: grouped by month, each line shows `[date] content`.
- **Search results**: ranked by similarity score.
- **Export (Markdown)**: `# My Memories` with monthly sections. Saved to `context-use-data/output/`.
- **Export (JSON)**: array of `{content, from_date, to_date}` objects.
- **Agent profile**: first-person Markdown printed to stdout.

## Error Handling & Stop Conditions

- **No API key**: commands that need OpenAI will prompt interactively or exit with guidance to run `context-use config set-key`.
- **No ZIP files found**: interactive mode shows guidance to place exports in `context-use-data/input/`.
- **Unknown provider**: CLI lists valid providers and exits.
- **No memories found**: list/search/export commands show a hint to run `context-use memories generate` first.
- **Batch API timeout**: memory generation polls automatically. If the batch takes long, the CLI keeps polling. Use `--quick` for faster feedback on small slices.
- **Rate limits in quick mode**: switch to the full pipeline (`context-use pipeline` without `--quick`) which uses the cheaper, rate-limit-friendly batch API.

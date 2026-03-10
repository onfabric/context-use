---
name: context-use
description: >
  Triggered when the user wants to turn data exports from ChatGPT,
  Claude, Instagram, or Google into searchable AI memory. Guides them
  through installing the CLI, downloading their export, generating
  memories, and putting those memories to use.
user-invocable: true
---

# context-use

Guide the user through turning their data exports into portable,
searchable AI memory with the `context-use` CLI.

## When to Use

- The user mentions wanting to extract memories from ChatGPT, Claude, Instagram, or Google data.
- The user asks how to make an AI agent remember things about them.
- The user has a data export ZIP and wants to do something with it.
- The user already has context-use installed and wants help with a specific command.

## Required Inputs

Gather these from the user before or during the workflow:

1. **Which provider** — ChatGPT, Claude, Instagram, or Google.
2. **Whether they already have the ZIP export** — if not, guide them to download it (Step 2).
3. **Whether they have an OpenAI API key** — needed for memory generation and search, not for ingest.

## Step-by-Step Workflow

### Step 1 — Install the CLI

Tell the user to install context-use:

```bash
pip install context-use
```

Or if they use `uv`:

```bash
uv tool install context-use
```

Verify it works:

```bash
context-use --version
```

### Step 2 — Help the user download their data export

The user needs a ZIP export from their provider. **Do not skip this step** —
most users won't have done this before. Walk them through it based on their
provider:

**ChatGPT:**
1. Go to https://chatgpt.com → Settings → Data Controls → Export Data.
2. Click "Export" — OpenAI will email a download link within a few minutes to a few hours.
3. Download the ZIP from the email. Do not extract it.

**Claude:**
1. Go to https://claude.ai → Settings → Account → Export Data.
2. Anthropic will email a download link.
3. Download the ZIP from the email. Do not extract it.

**Instagram:**
1. Open the Instagram app → Settings → Accounts Center → Your information and permissions → Download your information.
2. Select "Download or transfer information", pick the Instagram account, and choose "All available information".
3. Set the format to **JSON** (not HTML) and date range to "All time".
4. Request the download — Instagram will notify when it's ready (can take hours).
5. Download the ZIP. Do not extract it.

**Google:**
1. Go to https://takeout.google.com.
2. Deselect all, then select the products they want (Search, YouTube, etc.).
3. Choose export format: ZIP.
4. Request the export and download it when ready.

Once the user has the ZIP, tell them to either:
- Drop it into `context-use-data/input/`, or
- Note the file path to pass directly to the CLI.

### Step 3 — Set up the OpenAI API key

The user needs an OpenAI API key for memory generation and semantic search.
If they don't have one, direct them to https://platform.openai.com/api-keys.

```bash
context-use config set-key
```

This prompts them interactively. Alternatively:

```bash
context-use config set-key sk-...
# or
export OPENAI_API_KEY=sk-...
```

**If the user only wants to ingest** (parse the archive without generating
memories), the API key is not needed yet. They can set it up later.

### Step 4 — Run the pipeline

Recommend the approach based on the user's situation:

**First time / just want to try it out — use quick mode:**

```bash
context-use pipeline --quick path/to/export.zip
```

This uses the real-time API and only processes the last 30 days. Fast
feedback, results in seconds. Memories are exported to
`context-use-data/output/` as Markdown and JSON.

To include more history:

```bash
context-use pipeline --quick --last-days 90 path/to/export.zip
```

**Full export / production use — use the batch pipeline:**

```bash
context-use pipeline chatgpt path/to/export.zip
```

Or run without arguments for interactive archive picking:

```bash
context-use pipeline
```

This uses OpenAI's batch API — cheaper and rate-limit-friendly. Takes
2–10 minutes. All memories are persisted in a local SQLite database for
ongoing search and agent use.

**Step-by-step alternative** (useful for debugging or large archives):

```bash
context-use ingest chatgpt path/to/export.zip   # parse only, no API key needed
context-use memories generate                     # generate memories separately
```

### Step 5 — Explore the memories

Once memories are generated, help the user explore them:

**Browse everything:**

```bash
context-use memories list
context-use memories list --limit 20
```

**Semantic search** (find memories by meaning, not keywords):

```bash
context-use memories search "hiking trips"
context-use memories search "work stress" --from 2024-01-01 --to 2024-12-31
context-use memories search --top-k 5 "cooking recipes"
```

**Export to a file** for use elsewhere:

```bash
context-use memories export                        # Markdown (default)
context-use memories export --format json          # JSON
context-use memories export --out my-memories.md   # custom path
```

Exported files go to `context-use-data/output/` by default.

### Step 6 — Use the personal memory agent

The built-in agent can reason across the user's entire memory store.

**Synthesise pattern memories** — the agent deep-dives topic by topic and
creates higher-level memories that capture what is consistently true:

```bash
context-use agent synthesise
```

**Generate a user profile** — the agent compiles a first-person "who I am"
document from all memories:

```bash
context-use agent profile
```

**Ask anything** — send a free-form question or task to the agent:

```bash
context-use agent ask "What topics keep coming back across all my conversations?"
context-use agent ask "Fix any dates that look wrong in my memories"
```

The agent has full read/write access to memories — it can search, create,
update, and archive them.

### Step 7 — Ongoing management

Help the user with memory management as needed:

```bash
# View a specific memory
context-use memories get <memory-uuid>

# Manually create a memory
context-use memories create --content "I started learning piano" \
  --from 2024-03-01 --to 2024-03-31

# Edit a memory
context-use memories update <id> --content "Updated text"

# Archive superseded memories
context-use memories archive <id1> <id2> --superseded-by <new-id>

# Check settings
context-use config show

# Wipe everything and start fresh
context-use reset --yes
```

## Supported Providers

| Provider | Data types | Export guide |
|----------|------------|-------------|
| ChatGPT | Conversations | [Export your data](https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data) |
| Claude | Conversations | [Export your data](https://privacy.claude.com/en/articles/9450526-how-can-i-export-my-claude-data) |
| Instagram | Stories, Reels, Posts, Likes, Followers, Comments, Saved, Views, Searches | [Export your data](https://help.instagram.com/181231772500920) |
| Google | Searches, YouTube, Shopping, Discover, Lens | [Export your data](https://support.google.com/accounts/answer/3024190) |

## Configuration Reference

Config file location: `~/.config/context-use/config.toml`

| Setting | Env var | Default |
|---------|---------|---------|
| OpenAI API key | `OPENAI_API_KEY` | — |
| LLM model | `OPENAI_MODEL` | `gpt-5.2` |
| Embedding model | `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-large` |
| Database path | `CONTEXT_USE_DB_PATH` | `context_use.db` |
| Data directory | — | `./context-use-data` |

## Error Handling

- **User doesn't have the export yet:** Walk them through Step 2. Do not proceed until they have the ZIP.
- **No API key:** Guide them to https://platform.openai.com/api-keys and then `context-use config set-key`. If they only want to explore the raw archive, `ingest` works without a key.
- **Unknown provider:** Tell the user the supported list: chatgpt, claude, instagram, google.
- **No memories after generate:** The archive may have little content, or `--last-days` was too narrow. Suggest re-running with a wider window or the full pipeline.
- **Rate limits in quick mode:** Recommend switching to `context-use pipeline` (batch API) which is cheaper and rate-limit-friendly.
- **Export takes too long:** This is normal — Instagram and Google exports can take hours. The user just needs to wait for the provider's email/notification.

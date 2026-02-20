# context-use

Turn your data exports into AI memory. Import your Instagram or ChatGPT archives, generate first-person memories and a personal profile, then connect them to any AI assistant via MCP.

## How it works

```
Your archive (.zip)
      │
      ▼
   Ingest          Extract threads from your export
      │
      ▼
  Memories          LLM distills threads into first-person memories
      │
      ▼
   Profile          LLM builds a structured profile from your memories
      │
      ▼
  MCP Server        Expose profile + semantic search to any AI assistant
```

## Quick start

### 1. Install

```bash
# Requires Python 3.14+ and uv
uv pip install context-use

# Or clone and install locally
git clone https://github.com/onfabric/context-use.git
cd context-use
uv sync
```

### 2. Set up

```bash
context-use init
```

The setup wizard will:
- Start a local Postgres database (via Docker)
- Ask for your OpenAI API key
- Create the data directory structure and database tables

This creates a `data/` folder:

```
data/
  input/       ← drop your .zip archives here
  output/      ← exported memories and profiles
  storage/     ← internal extracted data
```

### 3. Ingest your data

Download your data export from [Instagram](https://help.instagram.com/181231772500920) or [ChatGPT](https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data), drop the `.zip` into `data/input/`, then run:

```bash
context-use ingest
```

This lists all archives in `data/input/`, lets you pick one, and auto-detects the provider. You can also pass arguments directly:

```bash
context-use ingest instagram ~/Downloads/instagram-export.zip
```

### 4. Generate memories

```bash
context-use memories generate
```

This submits batch jobs to OpenAI that distill your data into first-person memories. It typically takes 2-10 minutes.

### 5. Generate your profile

```bash
context-use profile generate
```

Creates a structured markdown profile summarising who you are, based on your memories.

### 6. Connect to an AI assistant

```bash
context-use server
```

This starts an MCP server that any compatible client can connect to. The command prints ready-to-paste configuration for Claude Desktop, Cursor, and other MCP clients.

## Commands

| Command | Description |
|---------|-------------|
| `context-use init` | Interactive setup wizard |
| `context-use ingest` | Pick & process an archive from `data/input/` |
| `context-use ingest <provider> <path>` | Process a specific archive |
| `context-use memories generate` | Generate memories from ingested data |
| `context-use memories list` | Browse your memories |
| `context-use memories search <query>` | Semantic search across memories |
| `context-use memories export` | Export memories to markdown or JSON |
| `context-use profile generate` | Generate or update your profile |
| `context-use profile show` | Display your current profile |
| `context-use profile export` | Export profile to markdown |
| `context-use server` | Start the MCP server |
| `context-use ask "<question>"` | Ask a question about your memories |

## Try the built-in agent

You don't need to set up an MCP client to test your memories. The `ask` command runs a simple RAG agent directly:

```bash
# One-shot question
context-use ask "What did I do last week?"

# Interactive chat
context-use ask --interactive
```

## Export your data

Export memories and profiles at any time. Files go to `data/output/` by default:

```bash
# Memories as markdown (grouped by month)
context-use memories export

# Memories as JSON
context-use memories export --format json

# Profile as markdown
context-use profile export

# Or specify a custom path
context-use memories export --out ~/Desktop/memories.md
```

## Supported providers

| Provider | Data types |
|----------|-----------|
| Instagram | Stories, Reels, DM conversations |
| ChatGPT | Conversations |

## Configuration

Configuration lives at `~/.config/context-use/config.toml` (created by `context-use init`). Environment variables take precedence:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `POSTGRES_HOST` | Database host |
| `POSTGRES_PORT` | Database port |
| `POSTGRES_DB` | Database name |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |
| `CONTEXT_USE_CONFIG` | Custom config file path |

## Prerequisites

- **Python 3.14+**
- **Docker** (for the local Postgres database, or provide your own Postgres with pgvector)
- **OpenAI API key** (for memory generation, embeddings, and search)

## MCP server

The MCP server exposes two tools to connected clients:

- **get_profile** — returns the user's profile as structured markdown
- **search** — semantic search over memories by query, date range, or both

### Connecting Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "context-use": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Connecting Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "context-use": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### stdio transport

For clients that prefer stdio (like some Claude Desktop configurations):

```bash
context-use server --transport stdio
```

## Development

```bash
uv sync
uv run pre-commit install
```

Run tests:

```bash
./scripts/prepare-tests.sh
./scripts/run-tests.sh
./scripts/shutdown-tests.sh
```

Type checking and linting:

```bash
uv run pyright
uv run ruff check --fix
uv run ruff format
```

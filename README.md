# context-use

Turn your data exports into portable AI memory.

## Features

- **Ingest** — parse provider export ZIPs into structured threads; no cloud upload required
- **Quickstart** — zero-database preview mode; results written to `data/output/` with no setup beyond an OpenAI key
- **Full pipeline** — persistent storage in PostgreSQL with pgvector; full archive history, batch API for cost-efficient memory generation
- **Semantic search** — `memories search` queries your memory store by meaning, not just keywords
- **Ask** — `ask` command for RAG-style Q&A grounded in your memories, including interactive chat mode
- **MCP server** — expose memories and semantic search to Claude Desktop, Cursor, or any MCP client
- **Personal agent** — multi-turn agent that synthesises higher-level pattern memories, generates a first-person profile, or runs ad-hoc queries against your memory store

## Supported providers

| Provider | Status | Data types | Export guide |
|----------|--------|------------|-------------|
| ChatGPT | Available | Conversations | [Export your data](https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data) |
| Instagram | Available | Stories, Reels, Posts | [Download your data](https://help.instagram.com/181231772500920) |
| WhatsApp | Coming soon | | |
| Google Takeout | Coming soon | | |

## Getting your export

1. Follow the export guide for your provider in the table above. The export is delivered as a ZIP file — **do not extract it**.
2. Move or copy the ZIP into `data/input/` inside the cloned repo:

```
context-use/
└── data/
    └── input/
        └── chatgpt-export.zip   ← place it here
```

Both `quickstart` and `pipeline` scan `data/input/` for exports on startup and prompt you to pick one if multiple are present.

## Install

```bash
git clone https://github.com/onfabric/context-use.git
cd context-use
uv sync
source .venv/bin/activate
```

Set your OpenAI API key:

```bash
context-use config set-key
# or: export OPENAI_API_KEY=sk-...
```

## Quick start

A zero-setup preview that requires no database.

```bash
context-use quickstart
```

The CLI prompts for the export and provider. Memory generation uses the OpenAI **real-time API** — fast for small slices but susceptible to rate limits on large exports. By default only the last 30 days are processed; use `--full` to include the complete history (the CLI warns you before proceeding).

The output is a snapshot: memories are written to `data/output/` as Markdown and JSON, then discarded. Nothing is stored in a database, so the memories are not queryable, searchable, or available to the MCP server after the command exits.

**The full pipeline is the intended way to use context-use beyond this initial preview.**

## Full pipeline

For persistent storage, semantic search, and the MCP server.

**1. Set up PostgreSQL (one-time)**

```bash
context-use config set-store postgres
```

Prompts to start a local container via Docker, then saves connection details to `~/.config/context-use/config.toml`. Skip Docker if you're bringing your own PostgreSQL instance.

**2. Run the pipeline**

```bash
context-use pipeline
```

Ingests the export and generates memories via the OpenAI **batch API** — significantly cheaper and more rate-limit-friendly than the real-time API used by quickstart. Typical runtime: 2–10 minutes. Memories are stored in PostgreSQL and persist across sessions, enabling semantic search, the `ask` command, the MCP server, and the personal agent.

**3. Explore your memories**

```bash
context-use memories list
context-use memories search "hiking trips in 2024"
context-use ask "What have I been cooking lately?"
context-use ask --interactive
```

## MCP server

Requires the full pipeline (PostgreSQL).

```bash
python -m context_use.ext.mcp_use.run
# use --transport stdio for clients that prefer stdio
```

Add to your MCP client config (Claude Desktop, Cursor, etc.):

```json
{
  "mcpServers": {
    "context-use": {
      "command": "python",
      "args": ["-m", "context_use.ext.mcp_use.run", "--transport", "stdio"]
    }
  }
}
```

Claude Desktop config path: `~/Library/Application Support/Claude/claude_desktop_config.json`. Cursor: Settings → MCP.

## Personal agent

A multi-turn agent that operates over your full memory store. Requires PostgreSQL.

```bash
context-use config set-agent adk
context-use agent synthesise          # generate higher-level pattern memories
context-use agent profile             # compile a first-person profile
context-use agent ask "What topics do I keep coming back to across all my conversations?"
```

## Configuration

Config file: `~/.config/context-use/config.toml`. Run `context-use config show` to see all active values and where each comes from (env var, file, or built-in default).

| Setting | CLI command | Env var | Default |
|---------|-------------|---------|---------|
| OpenAI API key | `config set-key` | `OPENAI_API_KEY` | — |
| Model | edit config file | `OPENAI_MODEL` | `gpt-5.2` |
| Embedding model | edit config file | `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-large` |
| Store backend | `config set-store postgres\|memory` | `CONTEXT_USE_STORE` | `memory` |
| PostgreSQL host | `config set-store postgres` | `POSTGRES_HOST` | `localhost` |
| PostgreSQL port | `config set-store postgres` | `POSTGRES_PORT` | `5432` |
| PostgreSQL database | `config set-store postgres` | `POSTGRES_DB` | `context_use` |
| PostgreSQL user | `config set-store postgres` | `POSTGRES_USER` | `postgres` |
| PostgreSQL password | `config set-store postgres` | `POSTGRES_PASSWORD` | `postgres` |
| Agent backend | `config set-agent adk` | `CONTEXT_USE_AGENT_BACKEND` | — |
| Data directory | edit config file | — | `./data` |

## Contributing

See `CONTRIBUTING.md` for architecture, how to add new providers and pipes, and the development setup.

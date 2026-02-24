# context-use

Turn your data exports into AI memory. Import your Instagram or ChatGPT archives, generate first-person memories and a personal profile, then connect them to any AI assistant via MCP.

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

## Supported providers

| Provider | Status | Data types | Export guide |
|----------|--------|------------|-------------|
| ChatGPT | Available | Conversations | [Export your data](https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data) |
| Instagram | Available | Stories, Reels, DM conversations | [Download your data](https://help.instagram.com/181231772500920) |
| WhatsApp | Coming soon | | |
| Google Takeout | Coming soon | | |

## Quick start

Download your data export from one of the supported providers above, then:

```bash
git clone https://github.com/onfabric/context-use.git
cd context-use
uv sync
export OPENAI_API_KEY=sk-...
context-use quickstart chatgpt ~/Downloads/export.zip
```

That's it. No database, no config file. Results are printed and exported to `data/output/`.

For persistent storage, semantic search, and the MCP server, set up PostgreSQL:

```bash
context-use config set-store postgres
```

Then use the step-by-step commands (`ingest`, `memories generate`, `profile generate`). Run `context-use --help` to see everything available — the CLI is self-documenting and prints next steps after every command.

## MCP server

```bash
python -m context_use.ext.mcp_use.run
```

Add the printed URL to your MCP client config (Claude Desktop, Cursor, etc). Use `--transport stdio` for clients that prefer stdio.

## Prerequisites

- Python 3.12+
- Docker (optional — for local Postgres via `context-use config set-store postgres`)
- OpenAI API key

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

For architecture, contributing guidelines, and how to add new providers and pipes, see `CLAUDE.md`.

# context-use

Turn your data exports into portable AI memory.

## Features

- **Ingest** — parse provider export ZIPs into structured threads; no cloud upload required
- **Quickstart** — zero-config preview mode; results written to `data/output/` with no setup beyond an OpenAI key
- **Full pipeline** — persistent storage in SQLite; full archive history, batch API for cost-efficient memory generation
- **Semantic search** — `memories search` queries your memory store by meaning, not just keywords
- **MCP server** — expose memories and semantic search to Claude Desktop, Cursor, or any MCP client
- **Personal agent** — multi-turn agent that synthesises higher-level pattern memories, generates a first-person profile, or runs ad-hoc queries against your memory store

## Supported providers

| Provider | Status | Data types | Export guide |
|----------|--------|------------|-------------|
| ChatGPT | Available | Conversations | [Export your data](https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data) |
| Instagram | Available | Stories, Reels, Posts | [Download your data](https://help.instagram.com/181231772500920) |
| WhatsApp | Coming soon | | |
| Google Takeout | Coming soon | | |

## Install

```bash
pip install context-use
# or
uv tool install context-use
```

## Quick start

A zero-setup preview that requires no database setup.

```bash
context-use pipeline --quick
```

The CLI prompts for the export and provider. Memory generation uses the OpenAI **real-time API** — fast for small slices but susceptible to rate limits on large exports. By default only the last 30 days are processed; use `--full` to include the complete history (the CLI warns you before proceeding).

## Getting your export

1. Follow the export guide for your provider in the table above. The export is delivered as a ZIP file — **do not extract it**.
2. Move or copy the ZIP into `data/input/` inside the cloned repo:

```
context-use/
└── data/
    └── input/
        └── chatgpt-export.zip   ← place it here
```

## Full pipeline

For full archive history and cost-efficient batch processing.

```bash
context-use pipeline
```

Ingests the export and generates memories via the OpenAI **batch API** — significantly cheaper and more rate-limit-friendly than the real-time API used by quickstart. Typical runtime: 2–10 minutes. Memories are stored in SQLite and persist across sessions, enabling semantic search, the MCP server, and the personal agent.

**Explore your memories**

```bash
context-use memories list
context-use memories search "hiking trips in 2024"
```

## MCP server

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

A multi-turn agent that operates over your full memory store.

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
| Agent backend | `config set-agent adk` | `CONTEXT_USE_AGENT_BACKEND` | — |
| Data directory | edit config file | — | `./data` |


## Adding new providers and pipes

See [AGENTS.md](AGENTS.md) for `context-use`'s architecture and how to add new providers and pipes.

## Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for how to contribute to the `context-use` project.

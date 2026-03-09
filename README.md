# context-use

![PyPI - Version](https://img.shields.io/pypi/v/context-use)

Turn your data exports into portable AI memory.

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

> [!WARNING]
> You must have an [export](#getting-your-export) from any of the [supported providers](#supported-providers) to use this command.

The CLI prompts for the export and provider. Memory generation uses the OpenAI **real-time API** — fast for small slices but susceptible to rate limits on large exports. By default only the last 30 days are processed; use `--full` to include the complete history (the CLI warns you before proceeding).

## Getting your export

1. Follow the export guide for your provider in the table above. The export is delivered as a ZIP file — **do not extract it**.
2. Move or copy the ZIP into `data/input/` inside the cloned repo:

```
context-use/
└── data/
    └── input/
        └── your-data-export.zip   ← place it here
```

## Supported providers

| Provider | Status | Data types | Export guide |
|----------|--------|------------|-------------|
| ChatGPT | Available | Conversations | [Export your data](https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data) |
| Instagram | Available | Stories, Reels, Posts | [Download your data](https://help.instagram.com/181231772500920) |
| WhatsApp | Coming soon | | |
| Google Takeout | Coming soon | | |

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
context-use memories export
```

## Personal agent

A multi-turn agent that operates over your full memory store.

```bash
context-use config set-agent adk
context-use agent synthesise          # generate higher-level pattern memories
context-use agent profile             # compile a first-person profile
context-use agent ask "What topics do I keep coming back to across all my conversations?"
```

## Configuration

There are a bunch of options you can configure:

```bash
context-use config --help
```

The configuration is saved in a config file at `<your-home-directory>/.config/context-use/config.toml`.


## Adding new providers and pipes

See [AGENTS.md](AGENTS.md) for `context-use`'s architecture and how to add new providers and pipes.

## Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for how to contribute to the `context-use` project.

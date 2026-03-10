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

Quickly extract memories (last 30 days) from your data export:

```bash
context-use pipeline --quick <your-zipped-data-export>
```

> [!IMPORTANT]
> You must have an [export](#getting-your-export) from any of the [supported providers](#supported-providers) to use this command.

The quickstart mode uses the **real-time API** of the LLM provider — fast for small slices but susceptible to rate limits on large exports. Use the [Full pipeline](#full-pipeline) to process the complete data export without incurring in rate limits.

## Full pipeline

For full data export and cost-efficient batch processing.

```bash
context-use pipeline
```

Ingests the export and generates memories via the **batch API** of the LLM provider — significantly cheaper and more rate-limit-friendly than the real-time API used by quickstart. Typical runtime: 2–10 minutes. Memories are stored in SQLite and persist across sessions, enabling semantic search and the [Personal agent](#personal-agent).

**Explore your memories**

```bash
context-use memories list
context-use memories search "hiking trips in 2024"
context-use memories export
```

## Personal agent

A multi-turn agent that operates over your full memory store.

```bash
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

## Getting your export

1. Follow the export guide for your provider in the [supported providers](#supported-providers) table. The export is delivered as a ZIP file — **do not extract it**.
2. Move or copy the ZIP into `context-use-data/input/`:

```
context-use-data/
└── input/
    └── your-data-export.zip   ← place it here
```

## Supported providers

| Provider | Status | Data types | Export guide |
|----------|--------|------------|-------------|
| ChatGPT | Available | Conversations | [Export your data](https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data) |
| Claude | Available | Conversations | [Export your data](https://privacy.claude.com/en/articles/9450526-how-can-i-export-my-claude-data) |
| Instagram | Available | Stories, Reels, Posts, Likes, Followers, ... | [Export your data](https://help.instagram.com/181231772500920) |
| Google | Coming soon | Searches, YouTube | [Export your data](https://support.google.com/accounts/answer/3024190) |
| WhatsApp | Coming soon | Conversations | [Export your data](https://faq.whatsapp.com/1180414079177245) |

# First-Time Setup

Read this when the preflight check shows `context-use` is not installed
or has no memories yet. Walk the user through each step — only proceed
when the previous step succeeds.

## Install

```bash
pip install context-use
```

Or with uv:

```bash
uv tool install context-use
```

Verify: `context-use --version`

## OpenAI API Key

Needed for memory generation and semantic search. If the user only wants
to ingest (parse the archive), the key isn't required yet.

```bash
context-use config set-key
```

This prompts interactively. Alternatively:

```bash
context-use config set-key sk-...
# or
export OPENAI_API_KEY=sk-...
```

If they don't have a key, point them to https://platform.openai.com/api-keys.

## Downloading a Data Export

The user needs a ZIP export from a supported provider. Guide them based
on which provider they use:

| Provider | How to export |
|----------|---------------|
| ChatGPT | https://chatgpt.com → Settings → Data Controls → Export Data. Download link arrives by email. |
| Claude | https://claude.ai → Settings → Account → Export Data. Download link arrives by email. |
| Instagram | Instagram app → Settings → Accounts Center → Your information and permissions → Download your information. Select **JSON** format (not HTML), "All time". Notification arrives when ready (can take hours). |
| Google | https://takeout.google.com → select products → export as ZIP. |

Tell the user not to extract the ZIP — the CLI reads it directly.

## Running the Pipeline

For a quick preview (real-time API, last 30 days):

```bash
context-use pipeline --quick path/to/export.zip
```

For the full export (batch API, cheaper, all history):

```bash
context-use pipeline chatgpt path/to/export.zip
```

Replace `chatgpt` with the provider: `chatgpt`, `claude`, `instagram`,
or `google`. Running without arguments starts interactive mode.

Verify memories were created:

```bash
context-use memories list --limit 5
```

## Configuration

```bash
context-use config show    # all settings and sources
context-use config path    # config file location
```

Config file: `~/.config/context-use/config.toml`

| Setting | Env var | Default |
|---------|---------|---------|
| API key | `OPENAI_API_KEY` | — |
| Model | `OPENAI_MODEL` | `gpt-5.2` |
| Embedding model | `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-large` |
| Database | `CONTEXT_USE_DB_PATH` | `context_use.db` |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Rate limits in quick mode | Use batch mode: `context-use pipeline` (without `--quick`) |
| No memories after pipeline | Archive may have little content, or `--last-days` too narrow. Try `--last-days 90` or omit for all history. |
| Export taking hours | Normal for Instagram and Google. User just needs to wait. |
| Reset everything | `context-use reset --yes` wipes all data. |

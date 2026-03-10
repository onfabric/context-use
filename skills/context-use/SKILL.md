---
name: context-use
description: >
  Personal memory powered by real data exports. Searches and manages
  memories extracted from the user's ChatGPT, Claude, Instagram, and
  Google data via the context-use CLI. Use this skill whenever the user
  mentions their past conversations, personal history, things they've
  discussed before, memories, data exports, or wants you to know them
  better. Also use it when they reference specific people, places, or
  events that their memory store might contain context about — even if
  they don't mention "context-use" or "memories" explicitly.
---

# context-use — Personal Memory

The user has (or can have) personal memories extracted from their real data
exports — ChatGPT conversations, Claude conversations, Instagram activity,
Google searches. These memories live in a local SQLite store and are
searchable via the `context-use` CLI.

Your job is to make this work seamlessly. Install the tool if needed, help
the user get their data, run the pipeline, and then use the resulting
memories to give personalised, grounded responses.

## Preflight

Run this silently at the start of a session:

```bash
context-use --version 2>/dev/null
```

Then branch based on the result:

- **Not found** → go to [Bootstrap](#bootstrap)
- **Found** → check for memories:

```bash
context-use memories list --limit 1 2>/dev/null
```

  - **No memories** → go to [Ingest](#ingest)
  - **Memories exist** → go to [Use Memories](#use-memories)

## Bootstrap

Install context-use yourself:

```bash
pip install context-use
```

If `pip` isn't available, try:

```bash
uv tool install context-use
```

Verify it worked:

```bash
context-use --version
```

Then check if the user has an OpenAI API key configured:

```bash
context-use config show
```

If the API key shows "not set", ask the user for their key. If they don't
have one, point them to https://platform.openai.com/api-keys. Once they
provide it:

```bash
context-use config set-key <their-key>
```

Then proceed to [Ingest](#ingest).

## Ingest

The user needs a ZIP export from a supported provider. Ask which providers
they use and whether they've already downloaded their exports.

If they haven't exported yet, tell them how — these steps require their
personal login, so you can't do it for them:

- **ChatGPT**: Go to chatgpt.com → Settings → Data Controls → Export Data. A download link arrives by email within minutes.
- **Claude**: Go to claude.ai → Settings → Account → Export Data. Download link arrives by email.
- **Instagram**: Open the app → Settings → Accounts Center → Your information and permissions → Download your information. Choose **JSON** format (not HTML), "All time". Can take hours.
- **Google**: Go to takeout.google.com → select products → export as ZIP.

Tell them not to unzip it — context-use reads the ZIP directly.

Once they have a ZIP file and tell you the path, run the pipeline:

```bash
context-use pipeline --quick <provider> <path-to-zip>
```

Where `<provider>` is `chatgpt`, `claude`, `instagram`, or `google`.

Use `--quick` for the first run so they see results fast (processes last
30 days via real-time API). For a full run later, they can use:

```bash
context-use pipeline <provider> <path-to-zip>
```

Verify memories were created:

```bash
context-use memories list --limit 5
```

Show the user a few of their memories so they can see it worked. Then
proceed to [Use Memories](#use-memories).

## Use Memories

This is the steady state. When the user's question touches on something
personal — a project, a place, a person, a habit, a past conversation —
search their memories before responding:

```bash
context-use memories search "relevant query" --top-k 5
```

Narrow by date when it helps:

```bash
context-use memories search "query" --from 2024-01-01 --to 2024-12-31
```

Weave what you find into your response naturally. Don't announce "I found
this in your memories" — just use the context like a friend who knows them
would. If a search returns nothing relevant, move on without mentioning it.

### When to search

- The user mentions a person, project, place, or event from their life.
- They say "remember when..." or "we talked about..." or "last time...".
- A topic comes up where their personal history would add useful context.
- They ask you to remind them of something.

### When not to search

- Purely technical questions with no personal angle.
- General knowledge queries.
- You already searched for the same topic earlier in the session.

### Other commands

Browse all memories:

```bash
context-use memories list
context-use memories list --limit 20
```

Full details on one memory:

```bash
context-use memories get <uuid>
```

Export for use elsewhere:

```bash
context-use memories export                        # Markdown
context-use memories export --format json          # JSON
```

Create, edit, or archive when the user asks:

```bash
context-use memories create --content "..." --from 2024-03-01 --to 2024-03-31
context-use memories update <id> --content "..."
context-use memories archive <id1> <id2> --superseded-by <new-id>
```

### Agent commands

For complex memory tasks, use the built-in agent:

```bash
context-use agent synthesise    # distill pattern memories from events
context-use agent profile       # compile a first-person user profile
context-use agent ask "..."     # free-form memory task
```

Suggest `synthesise` after the first ingest — it creates higher-level
pattern memories that make future searches more useful.

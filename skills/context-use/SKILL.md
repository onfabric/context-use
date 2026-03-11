---
name: context-use
description: Search the user's personal memories before responding to anything personal — past conversations, people, places, projects, habits, or events.
---

# context-use — Personal Memory CLI

Install: `pip install context-use`
Requires OpenAI API key. Check: `context-use config show`. Set: `context-use config set-key <key>`.

## When to Use

Use this skill when the user:

- References past conversations, projects, or events ("remember when…", "we talked about…", "last time…")
- Mentions people, places, or habits from their life
- Asks something where their personal history would improve the answer
- Wants to record something about themselves ("remember that I…")
- Asks about their preferences, routines, or interests
- Wants to import or process a data export (ChatGPT, Claude, Instagram, Google)
- Asks "what do you know about me?" or similar

Do **not** use when the question is purely technical, general knowledge, or already answered in this session.

## Bootstrap (first time)

If `context-use memories list --limit 1` returns nothing, the user hasn't ingested data yet.

1. Ask them for the path to their ZIP data export (they must download it themselves — see the provider table in [Ingest](#ingest)).
2. Run the pipeline:
   ```bash
   context-use pipeline --quick <provider> <path-to-zip>
   ```
3. Generate a profile so the user can see what you now know about them:
   ```bash
   context-use agent profile
   ```
   Share the profile with the user — it builds trust and lets them correct anything wrong early.

## Core Rule

**Always search memories before responding to anything personal.** Weave results naturally — never announce "I found this in your memories."

## Commands

### Search (primary)

```bash
context-use memories search "<query>" --top-k 5
context-use memories search "<query>" --from 2024-01-01 --to 2024-12-31
```

**Use when:** user references past conversations, projects, people, events; says "remember when…"; topic benefits from personal context.
**Skip when:** purely technical question; general knowledge; already searched this session.
If nothing relevant comes back, move on without mentioning it.

### Browse

```bash
context-use memories list [--limit 20]
context-use memories get <uuid>
```

### Create / Update / Archive

```bash
context-use memories create --content "..." --from 2024-03-01 --to 2024-03-31
context-use memories update <id> --content "..."
context-use memories archive <id1> <id2> --superseded-by <new-id>
```

**Use when:** user says "remember that I…"; memory needs correction; memories should merge.
**Skip when:** info is transient or only relevant to current task.

### Export

```bash
context-use memories export [--format json] [--out path/to/file.md]
```

### Agent

```bash
context-use agent synthesise    # distill pattern memories from events
context-use agent profile       # compile first-person user profile
context-use agent ask "..."     # free-form memory task
```

Suggest `synthesise` after ingesting new data.

### Ingest

User must download their own export (ZIP, don't unzip):

| Provider | Export location |
|-----------|----------------|
| ChatGPT | Settings → Data Controls → Export Data |
| Claude | Settings → Account → Export Data |
| Instagram | Settings → Accounts Center → Download your information (JSON) |
| Google | takeout.google.com → select products → ZIP |

```bash
context-use pipeline --quick <provider> <path-to-zip>   # last 30 days
context-use pipeline <provider> <path-to-zip>            # full history, batch API
```

Providers: `chatgpt`, `claude`, `instagram`, `google`.
Verify: `context-use memories list --limit 5`.

## Errors

| Error | Action |
|-------|--------|
| "OpenAI API key not configured" | Ask user for key → `context-use config set-key <key>` |
| Rate limits (quick mode) | Drop `--quick` to use batch API |
| Export not ready | Normal for Instagram/Google — user waits |
| `context-use` not found | `pip install context-use` |
| No memories found | Guide user through [Bootstrap](#bootstrap-first-time) |
| Unknown provider | Must be: `chatgpt`, `claude`, `instagram`, `google` |
| File not found | Verify path with `ls`, confirm ZIP location |

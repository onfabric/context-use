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

The user has personal memories extracted from their real data (ChatGPT
conversations, Claude conversations, Instagram activity, Google searches).
These memories live in a local SQLite store and are searchable via the
`context-use` CLI.

Your job is to use these memories to give more personalised, grounded
responses. When a topic comes up that the user's history might cover,
search their memories before answering. Reference specific details — names,
places, dates, projects — rather than being generic.

## Preflight

Run this once per session to figure out the user's setup state:

```bash
context-use --version 2>/dev/null && context-use memories list --limit 1
```

**If `context-use` is not found** — the user hasn't installed it yet.
Read `references/setup.md` and walk them through first-time setup.

**If the command works but returns no memories** — the tool is installed
but the pipeline hasn't been run yet. Ask the user if they have a data
export ZIP ready, and if so, guide them through running the pipeline
(see `references/setup.md`, "Running the Pipeline" section).

**If memories are returned** — you're good. Use them.

## Searching Memories

This is the core of the skill. When the user's question touches on
something personal — a project they mentioned, a place they visited,
a person they talked about, a habit or pattern — search before responding:

```bash
context-use memories search "relevant query" --top-k 5
```

Narrow by date when it helps:

```bash
context-use memories search "query" --from 2024-01-01 --to 2024-12-31
```

Weave what you find into your response naturally. Don't say "according to
your memories" every time — just use the context the way a friend who knows
them would. If a search returns nothing relevant, move on without mentioning
it.

## Other Memory Commands

Browse everything:

```bash
context-use memories list
context-use memories list --limit 20
```

Full details on one memory:

```bash
context-use memories get <uuid>
```

Create, edit, or archive memories when the user asks:

```bash
context-use memories create --content "..." --from 2024-03-01 --to 2024-03-31
context-use memories update <id> --content "..." --from ... --to ...
context-use memories archive <id1> <id2> --superseded-by <new-id>
```

Export for use elsewhere:

```bash
context-use memories export                        # Markdown
context-use memories export --format json          # JSON
context-use memories export --out path/to/file.md  # custom path
```

## Personal Agent

For complex memory tasks the user can't do with a single command,
context-use has a built-in agent:

```bash
context-use agent synthesise    # distill pattern memories from event memories
context-use agent profile       # compile a first-person user profile
context-use agent ask "..."     # free-form memory task
```

Suggest `synthesise` if the user has a lot of raw memories but hasn't
extracted patterns yet. Suggest `profile` if they want a summary of who
they are based on their data.

## When Not to Search

Don't search memories for every message. Skip it when:

- The conversation is purely technical with no personal angle.
- The user is asking about general knowledge, not their own history.
- You've already searched for the same topic earlier in the conversation.

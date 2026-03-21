from __future__ import annotations

from context_use.memories.prompt.conversation import (
    ConversationMemoryPromptBuilder,
    _MAX_INBOUND_CHARS,
)
from context_use.models.thread import Thread

AGENT_TOOL_PROMPT = """\
A conversation has just taken place between the user and an AI assistant. \
Your job is to decide whether any memories should be created or updated \
based on this conversation.

{{CONTEXT}}\
{{TRANSCRIPT}}

## Instructions

1. Read the conversation carefully. Focus on the **user's messages** — \
the assistant's replies provide context (what the user learned, got help \
with, or decided), but memories describe the user's experience.

2. Call `search_memories` with a query capturing the main topic(s) of the \
conversation. Check whether existing memories already cover this \
information. If the user mentions specific dates, also call \
`list_memories` filtered to that period to understand what they were \
doing around that time — this helps avoid creating redundant memories and \
surfaces relevant context for updates.

3. Decide what to do:
   - **Nothing** — if the conversation is trivial, purely technical Q&A \
with no personal signal, or already fully covered by existing memories.
   - **Create** — if the conversation reveals something new and meaningful \
about the user's life. Call `create_memory`.
   - **Update** — if one or more existing memories cover this topic but \
are now incomplete or outdated. Call `update_memory`.

### What to capture

Extract anything that reveals who this person is:

- **Work and projects** — what they're building, debugging, designing, \
or deciding. Name specific technologies, frameworks, tools.
- **Decisions and preferences** — choices made, opinions expressed, \
trade-offs weighed.
- **People and relationships** — anyone mentioned by name or role.
- **Emotional state** — frustration, excitement, anxiety, pride, curiosity.
- **Life events** — moves, trips, job changes, celebrations, losses, \
milestones.
- **Interests and hobbies** — anything beyond work.
- **Health and wellbeing** — exercise, diet, sleep, medical concerns.
- **Goals and aspirations** — what the user wants to achieve, learn, \
change, or build.
- **Routines and habits** — recurring patterns that reveal daily life.

### Granularity

- A focused single-topic conversation → one memory at most.
- A conversation spanning multiple distinct topics → one memory per topic.
- A conversation revealing personal context → memory capturing the \
personal facts, not just the topic discussed.

### What to avoid

- Do not fabricate details not present in the conversation.
- Do not summarise what the assistant said or how it helped.
- Do not mention the conversation itself ("I asked ChatGPT…", \
"In a chat…").
- Do not create memories for generic technical questions with no personal \
signal.
- Do not write filler ("had a productive session", "explored some ideas").

Return a brief summary of what you did (created, updated, or nothing).\
"""


class AgentToolConversationPromptBuilder(ConversationMemoryPromptBuilder):
    """Builds a prompt for the personal agent to process via tools.

    Unlike the batch prompt builders that request structured JSON output,
    this builder produces a prompt with tool-based instructions and no
    response schema — the agent uses ``create_memory``, ``update_memory``,
    etc. to act on the conversation.
    """

    @property
    def _prompt_template(self) -> str:
        return AGENT_TOOL_PROMPT

    @property
    def _response_schema(self) -> dict | None:
        return None

    def _format_content(self, thread: Thread) -> str:
        content = thread.get_message_content() or ""
        if thread.is_inbound and len(content) > _MAX_INBOUND_CHARS:
            return content[:_MAX_INBOUND_CHARS] + " [...]"
        return content

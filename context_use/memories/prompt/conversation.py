from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from collections.abc import Callable

from context_use.llm.base import PromptItem
from context_use.memories.prompt.base import BasePromptBuilder, MemorySchema
from context_use.models.thread import Thread
from context_use.prompt_categories import WHAT_TO_CAPTURE

OUTPUT_FORMAT = """\
## Output format
Return a JSON object with a ``memories`` array. Each memory has:
- ``content``: the memory text (1-2 sentences, detail-rich, first-person).
- ``from_date``: start date (YYYY-MM-DD).
- ``to_date``: end date (YYYY-MM-DD, same as from_date for single-day).
"""

_SHARED_BODY = (
    WHAT_TO_CAPTURE
    + """

### Level of abstraction

Ask yourself: **what does this conversation reveal about who this person \
is?** Write at that level — not at the level of individual steps, \
commands, or messages.

- If they used Docker, the memory is "I work with Docker" — not \
"I ran docker ps and got an error."
- If they debugged a Node.js app, the memory is "I'm building a \
Node.js app with MySQL" — not "I hit a Knex connection error."
- If they asked about travel logistics, the memory is "I'm planning \
a trip from Milan to Sestri Levante" — not "I looked up train \
schedules."
- If several messages are just quick Q&A with no personal revelation \
(e.g. "what does this error mean?"), they may not warrant a memory \
at all.

### What makes a good memory

- **Identity facts**: where the person lives, what they do for work, \
what languages they speak, what tools they use regularly.
- **Feelings and motivations**: why they care, how they feel, what \
they're uncertain or excited about. These are more valuable than \
technical steps.
- **Relationships and social context**: people mentioned, social \
dynamics, plans with others.
- **Patterns over episodes**: "I use Docker often" is better than \
"I ran a Docker command once." Prefer the durable fact over the \
transient event.

### What to avoid

- Do not fabricate details not present in the conversation.
- Do not write filler ("had a productive session", "explored some ideas").
- Do not capture procedural steps (specific commands, error messages, \
API calls). Capture what the person was *trying to do* and *why*, \
not how.
- Do not ignore non-technical content — a conversation about planning a \
birthday party is just as important as one about debugging code.

{{CONTEXT}}\
{{TRANSCRIPT}}

"""
    + OUTPUT_FORMAT
)

AGENT_PROMPT_OVERRIDE = Path(__file__).with_name("overrides") / "agent_conversation.txt"

AGENT_CONVERSATION_MEMORIES_PROMPT = (
    """\
You are given a conversation between a user and an AI assistant.

## Your task

Extract the user's **memories** from this conversation. A memory captures \
something meaningful about the user's life — written from their perspective \
as a first-person journal entry.

**Focus on the user's messages.** The assistant's replies provide context \
(what the user learned, got help with, or decided), but memories should \
describe the user's experience, not the assistant's answers.

### What to avoid (additional)

- Do not summarize what the assistant said or how it helped.
- Do not mention the conversation itself ("I asked ChatGPT…", "In a chat…").

"""
    + _SHARED_BODY
)

HUMAN_CONVERSATION_MEMORIES_PROMPT = (
    """\
You are given a conversation between the user and another person.

## Your task

Extract the user's **memories** from this conversation. A memory captures \
something meaningful about the user's life — written from their perspective \
as a first-person journal entry.

Both sides of the conversation matter equally. The user's replies, what \
others shared, plans made together, and topics discussed all reflect \
the user's life.

### What to avoid (additional)

- Do not mention the conversation itself ("In a chat…", "I texted…").

"""
    + _SHARED_BODY
)

_MAX_INBOUND_CHARS = 2000


def format_transcript(
    threads: list[Thread],
    *,
    content_fn: Callable[[Thread], str] | None = None,
) -> str:
    _content = content_fn or (lambda t: t.get_message_content() or "")
    lines: list[str] = []
    prev_was_inbound: bool | None = None
    for t in threads:
        role = t.get_participant_label().upper()
        ts = t.asat.strftime("%Y-%m-%d %H:%M")
        content = _content(t)
        if prev_was_inbound is not None and prev_was_inbound and not t.is_inbound:
            lines.append("")
        lines.append(f"[{role} {ts}] {content}")
        prev_was_inbound = t.is_inbound
    return "## Transcript\n\n" + "\n".join(lines)


class ConversationMemoryPromptBuilder(BasePromptBuilder):
    """Abstract base for conversation-based memory prompt builders.

    Subclasses supply a prompt template and may override ``_format_content``
    to control per-message content rendering (e.g. truncation).
    """

    @property
    @abstractmethod
    def _prompt_template(self) -> str: ...

    def has_content(self) -> bool:
        return any(ctx.new_threads for ctx in self.contexts)

    def build(self) -> list[PromptItem]:
        response_schema = MemorySchema.json_schema()

        items: list[PromptItem] = []
        for ctx in self.contexts:
            if not ctx.new_threads:
                continue

            threads = sorted(ctx.new_threads, key=lambda t: t.asat)
            transcript = format_transcript(threads, content_fn=self._format_content)
            context_block = self._format_context(ctx)

            prompt = self._prompt_template.replace(
                "{{CONTEXT}}", context_block
            ).replace("{{TRANSCRIPT}}", transcript)

            items.append(
                PromptItem(
                    item_id=ctx.group_id,
                    prompt=prompt,
                    response_schema=response_schema,
                )
            )
        return items

    def _format_content(self, thread: Thread) -> str:
        return thread.get_message_content() or ""


class AgentConversationMemoryPromptBuilder(ConversationMemoryPromptBuilder):
    """Builds memory prompts for conversations with an AI assistant."""

    @property
    def _prompt_template(self) -> str:
        try:
            if AGENT_PROMPT_OVERRIDE.is_file():
                return AGENT_PROMPT_OVERRIDE.read_text()
        except OSError:
            pass
        return AGENT_CONVERSATION_MEMORIES_PROMPT

    def _format_content(self, thread: Thread) -> str:
        content = thread.get_message_content() or ""
        if thread.is_inbound and len(content) > _MAX_INBOUND_CHARS:
            return content[:_MAX_INBOUND_CHARS] + " [...]"
        return content


class HumanConversationMemoryPromptBuilder(ConversationMemoryPromptBuilder):
    """Builds memory prompts for conversations between people."""

    @property
    def _prompt_template(self) -> str:
        return HUMAN_CONVERSATION_MEMORIES_PROMPT

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable

from context_use.facets.types import render_facet_types_section
from context_use.llm.base import PromptItem
from context_use.memories.prompt.base import BasePromptBuilder, MemorySchema
from context_use.models.thread import Thread
from context_use.prompt_categories import WHAT_TO_CAPTURE

_FACETS_SECTION = render_facet_types_section()

_SHARED_BODY = (
    WHAT_TO_CAPTURE
    + """

### Granularity

Let the content guide you:
- A focused single-topic conversation → one memory.
- A conversation spanning multiple distinct topics → one memory per topic.
- A deep dive → memory capturing the key problem and outcome.
- A conversation revealing personal context → memory capturing the \
personal facts, not just the topic discussed.

Generate as many memories as the content warrants.

### Detail level

Each memory should be **information-dense**:
- Use specific names: people, places, technologies, brands — not vague \
categories.
- Describe the user's specific situation, not just the general topic.
- Include concrete details that distinguish this from a generic summary.
- Capture the user's reasoning when they explained why they chose \
something or how they felt about it.
- When the user learned something or got an answer, capture what they \
learned — that's now part of their knowledge.

### What to avoid

- Do not fabricate details not present in the conversation.
- Do not write filler ("had a productive session", "explored some ideas").
- Do not ignore non-technical content — a conversation about planning a \
birthday party is just as important as one about debugging code.

{{CONTEXT}}\
{{TRANSCRIPT}}

## Output format
Return a JSON object with a ``memories`` array. Each memory has:
- ``content``: the memory text (1-2 sentences, detail-rich, first-person).
- ``from_date``: start date (YYYY-MM-DD).
- ``to_date``: end date (YYYY-MM-DD, same as from_date for single-day).
- ``facets``: an array of semantic facets extracted from the memory. Each facet has:
  - ``facet_type``: one of the types defined below.
  - ``facet_value``: the specific extracted value.
"""
    + _FACETS_SECTION
)

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

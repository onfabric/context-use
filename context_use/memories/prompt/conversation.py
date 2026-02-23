from __future__ import annotations

from dataclasses import dataclass

from context_use.llm.base import PromptItem
from context_use.memories.prompt.base import (
    BasePromptBuilder,
    GroupContext,
    MemorySchema,
)
from context_use.models.thread import Thread

CONVERSATION_MEMORIES_PROMPT = """\
You are given a conversation between a user and an AI assistant.

**Period:** {{FROM_DATE}} to {{TO_DATE}}

## Your task

Extract the user's **memories** from this conversation. A memory captures \
something meaningful about the user's life — written from their perspective \
as a first-person journal entry.

**Focus on the user's messages.** The assistant's replies provide context \
(what the user learned, got help with, or decided), but memories should \
describe the user's experience, not the assistant's answers.

### What to capture

Extract anything that reveals who this person is:

- **Work and projects** — what they were building, debugging, designing, \
or deciding. Name specific technologies, frameworks, tools.
- **Decisions and preferences** — choices made, opinions expressed, \
trade-offs weighed. These reveal how the user thinks.
- **People and relationships** — anyone mentioned by name or role \
(partner, colleague, friend, family member). Note the relationship and \
any context about that person.
- **Emotional state** — frustration, excitement, anxiety, pride, \
uncertainty, curiosity. How the user felt about what they were doing.
- **Life events** — moves, trips, job changes, celebrations, losses, \
health issues, milestones. These anchor who the user is in time.
- **Interests and hobbies** — books, music, cooking, fitness, travel, \
games, creative projects — anything beyond work.
- **Health and wellbeing** — exercise routines, dietary choices, sleep, \
medical concerns, mental health.
- **Values and beliefs** — positions taken, principles expressed, things \
the user cares about or pushes back on.
- **Goals and aspirations** — what the user wants to achieve, learn, \
change, or build in the future.
- **Personal context** — role, location, background, constraints, \
routines, habits.

### Granularity

Let the content guide you:
- A focused single-topic conversation → one memory.
- A conversation spanning multiple distinct topics → one memory per topic.
- A deep dive → memory capturing the key problem and outcome.
- A conversation revealing personal context → memory capturing the \
personal facts, not just the topic discussed.

Generate between {{MIN_MEMORIES}} and {{MAX_MEMORIES}} memories.

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

- Do not summarize what the assistant said or how it helped.
- Do not mention the conversation itself ("I asked ChatGPT…", \
"In a chat…").
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
"""


MAX_ASSISTANT_CHARS = 2000


@dataclass(frozen=True)
class ConversationConfig:
    """Controls memory extraction from conversation threads."""

    max_memories: int = 5
    min_memories: int = 1
    max_assistant_chars: int = MAX_ASSISTANT_CHARS


class ConversationMemoryPromptBuilder(BasePromptBuilder):
    """Build one ``PromptItem`` per conversation group.

    Groups are keyed by conversation / collection ID.  Each prompt
    contains the full transcript with ``[USER]`` and ``[ASSISTANT]``
    labels so the LLM can distinguish roles and focus on user intent.
    """

    def __init__(
        self,
        contexts: list[GroupContext],
        config: ConversationConfig | None = None,
    ) -> None:
        super().__init__(contexts)
        self.config = config or ConversationConfig()

    def has_content(self) -> bool:
        return any(ctx.new_threads for ctx in self.contexts)

    def build(self) -> list[PromptItem]:
        response_schema = MemorySchema.json_schema()

        items: list[PromptItem] = []
        for ctx in self.contexts:
            if not ctx.new_threads:
                continue

            threads = sorted(ctx.new_threads, key=lambda t: t.asat)
            from_date = threads[0].asat.date()
            to_date = threads[-1].asat.date()

            user_count = sum(1 for t in threads if not t.is_inbound)
            min_mem, max_mem = self._memory_bounds(user_count)

            transcript = self._format_transcript(threads)
            context_block = self._format_context(ctx)

            prompt = (
                CONVERSATION_MEMORIES_PROMPT.replace(
                    "{{FROM_DATE}}", from_date.isoformat()
                )
                .replace("{{TO_DATE}}", to_date.isoformat())
                .replace("{{MIN_MEMORIES}}", str(min_mem))
                .replace("{{MAX_MEMORIES}}", str(max_mem))
                .replace("{{CONTEXT}}", context_block)
                .replace("{{TRANSCRIPT}}", transcript)
            )

            items.append(
                PromptItem(
                    item_id=ctx.group_id,
                    prompt=prompt,
                    response_schema=response_schema,
                )
            )
        return items

    def _memory_bounds(self, user_message_count: int) -> tuple[int, int]:
        """Scale max memories with conversation length."""
        max_m = max(1, min(self.config.max_memories, 1 + user_message_count // 5))
        return self.config.min_memories, max_m

    @staticmethod
    def _get_conversation_title(threads: list[Thread]) -> str | None:
        for t in threads:
            obj = t.payload.get("object", {})
            ctx = obj.get("context", {})
            name = ctx.get("name")
            if name:
                return str(name)
        return None

    def _format_transcript(self, threads: list[Thread]) -> str:
        title = self._get_conversation_title(threads)
        header = f'## Conversation: "{title}"\n\n' if title else "## Transcript\n\n"

        limit = self.config.max_assistant_chars
        lines: list[str] = []
        prev_role: str | None = None
        for t in threads:
            role = "USER" if not t.is_inbound else "ASSISTANT"
            ts = t.asat.strftime("%Y-%m-%d %H:%M")
            content = t.get_message_content() or ""
            if role == "ASSISTANT" and len(content) > limit:
                content = content[:limit] + " [...]"
            if prev_role is not None and role != prev_role and role == "USER":
                lines.append("")
            lines.append(f"[{role} {ts}] {content}")
            prev_role = role

        return header + "\n".join(lines)

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
what the user was trying to accomplish, learn, decide, or build — written \
from the user's perspective as if they are journaling about their work and \
interests.

**Focus on the user's messages.** The assistant's replies provide context \
for understanding the user's goal, but memories should describe the user's \
experience — what they were working on, what they decided, what they learned.

### What to capture

- The topic, problem, or project the user was exploring.
- Key decisions or preferences the user expressed.
- Technologies, tools, frameworks, or APIs the user worked with.
- Personal context the user revealed (role, location, goals, constraints).
- Specific outcomes: what the user built, fixed, learned, or decided.

### Granularity

Let the content guide you:
- A focused single-topic conversation → one memory.
- A conversation spanning multiple distinct topics → one memory per topic.
- A deep technical dive → memory capturing the key problem and solution.

Generate between {{MIN_MEMORIES}} and {{MAX_MEMORIES}} memories.

### Detail level

Each memory should be **information-dense**:
- Name specific technologies, libraries, APIs, error messages, or design \
choices.
- Describe the user's specific goal, not just the general topic.
- Include concrete details: file names, config values, architecture \
decisions.
- Capture the user's reasoning when they explained trade-offs.

### What to avoid

- Do not summarize what the assistant said.
- Do not mention the conversation itself ("I asked ChatGPT…", \
"In a chat…").
- Do not fabricate details not present in the conversation.
- Do not write filler ("had a productive session").

{{CONTEXT}}\
{{TRANSCRIPT}}

## Output format
Return a JSON object with a ``memories`` array. Each memory has:
- ``content``: the memory text (1-2 sentences, detail-rich, first-person).
- ``from_date``: start date (YYYY-MM-DD).
- ``to_date``: end date (YYYY-MM-DD, same as from_date for single-day).
"""


@dataclass(frozen=True)
class ConversationConfig:
    """Controls memory extraction from conversation threads."""

    max_memories: int = 5
    min_memories: int = 1


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

    def _format_transcript(self, threads: list[Thread]) -> str:
        lines: list[str] = []
        for t in threads:
            role = "USER" if not t.is_inbound else "ASSISTANT"
            ts = t.asat.strftime("%Y-%m-%d %H:%M")
            content = t.get_message_content() or ""
            lines.append(f"[{role} {ts}] {content}")

        return "## Transcript\n\n" + "\n".join(lines)

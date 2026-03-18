from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from context_use.facade.core import ContextUse
    from context_use.store.base import MemorySearchResult

logger = logging.getLogger(__name__)

type Message = dict[str, Any]

CONTEXT_PREAMBLE = (
    "The following are relevant memories about the user. "
    "Use them to personalise your response when appropriate."
)


def extract_last_user_message(messages: list[Message]) -> str | None:
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [
                part["text"]
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            return " ".join(texts) if texts else None
    return None


def format_memory_context(results: list[MemorySearchResult]) -> str:
    lines: list[str] = []
    for r in results:
        period = f"{r.from_date.isoformat()} to {r.to_date.isoformat()}"
        lines.append(f"- [{period}] {r.content}")
    body = "\n".join(lines)
    return f"<user_context>\n{CONTEXT_PREAMBLE}\n{body}\n</user_context>"


def inject_context(messages: list[Message], context: str) -> list[Message]:
    result = copy.deepcopy(messages)
    for msg in result:
        if msg.get("role") == "system":
            current = msg.get("content", "")
            if isinstance(current, str):
                msg["content"] = f"{current}\n\n{context}" if current else context
            return result
    result.insert(0, {"role": "system", "content": context})
    return result


async def enrich_messages(
    messages: list[Message],
    ctx: ContextUse,
    *,
    top_k: int = 5,
) -> list[Message]:
    query = extract_last_user_message(messages)
    if query is None:
        return messages

    try:
        results = await ctx.search_memories(query=query, top_k=top_k)
    except Exception:
        logger.warning(
            "Memory search failed, forwarding without enrichment", exc_info=True
        )
        return messages

    if not results:
        logger.debug("No memories found for query")
        return messages

    from context_use.proxy.log import log_enrichment

    log_enrichment(results)
    context = format_memory_context(results)
    return inject_context(messages, context)

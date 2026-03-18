from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from context_use.facade.core import ContextUse
    from context_use.store.base import MemorySearchResult

logger = logging.getLogger(__name__)

type Message = dict[str, Any]

_TEXT_CONTENT_TYPES = ("text", "input_text")

CONTEXT_PREAMBLE = (
    "The following are relevant memories about the user. "
    "Use them to personalise your response when appropriate."
)


def extract_last_user_query(
    input_data: str | list[dict[str, Any]],
) -> str | None:
    if isinstance(input_data, str):
        return input_data or None

    for item in reversed(input_data):
        if item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            return content or None
        if isinstance(content, list):
            texts = [
                part["text"]
                for part in content
                if isinstance(part, dict) and part.get("type") in _TEXT_CONTENT_TYPES
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


async def enrich_body(
    body: dict[str, Any],
    ctx: ContextUse,
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    query_source, query = _extract_query(body)
    if query is None:
        return body

    try:
        results = await ctx.search_memories(query=query, top_k=top_k)
    except Exception:
        logger.warning(
            "Memory search failed, forwarding without enrichment", exc_info=True
        )
        return body

    if not results:
        logger.debug("No memories found for query")
        return body

    previews = ", ".join(
        f"{r.id} ({r.content[:40]}…)"
        if len(r.content) > 40
        else f"{r.id} ({r.content})"
        for r in results
    )
    logger.info("Enriching with %d memories: %s", len(results), previews)
    context = format_memory_context(results)

    if query_source == "messages":
        return {**body, "messages": inject_context(body["messages"], context)}

    instructions = body.get("instructions")
    return {
        **body,
        "instructions": (f"{instructions}\n\n{context}" if instructions else context),
    }


def _extract_query(body: dict[str, Any]) -> tuple[str, str | None]:
    if "messages" in body:
        return "messages", extract_last_user_query(body["messages"])
    input_data = body.get("input")
    if input_data is None:
        return "input", None
    return "input", extract_last_user_query(input_data)

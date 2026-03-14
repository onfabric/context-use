from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

from context_use.proxy.enrichment import (
    CONTEXT_PREAMBLE,
    enrich_messages,
    extract_last_user_message,
    format_memory_context,
    inject_context,
)
from context_use.store.base import MemorySearchResult


def _make_result(
    content: str = "Likes pizza",
    from_date: date = date(2024, 1, 1),
    to_date: date = date(2024, 1, 15),
    similarity: float = 0.95,
) -> MemorySearchResult:
    return MemorySearchResult(
        id="mem-1",
        content=content,
        from_date=from_date,
        to_date=to_date,
        similarity=similarity,
    )


class TestExtractLastUserMessage:
    def test_string_content(self) -> None:
        messages = [
            {"role": "system", "content": "Be helpful"},
            {"role": "user", "content": "What food do I like?"},
        ]
        assert extract_last_user_message(messages) == "What food do I like?"

    def test_list_content_with_text(self) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {"type": "image_url", "image_url": {"url": "https://..."}},
                ],
            },
        ]
        assert extract_last_user_message(messages) == "Describe this image"

    def test_list_content_multiple_text_parts(self) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": "world"},
                ],
            },
        ]
        assert extract_last_user_message(messages) == "Hello world"

    def test_list_content_no_text_parts(self) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "https://..."}},
                ],
            },
        ]
        assert extract_last_user_message(messages) is None

    def test_no_user_message(self) -> None:
        messages = [
            {"role": "system", "content": "Be helpful"},
            {"role": "assistant", "content": "Hi!"},
        ]
        assert extract_last_user_message(messages) is None

    def test_empty_messages(self) -> None:
        assert extract_last_user_message([]) is None

    def test_picks_last_user_message(self) -> None:
        messages = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "Answer"},
            {"role": "user", "content": "Follow up"},
        ]
        assert extract_last_user_message(messages) == "Follow up"


class TestFormatMemoryContext:
    def test_single_result(self) -> None:
        results = [_make_result()]
        text = format_memory_context(results)
        assert "<user_context>" in text
        assert "</user_context>" in text
        assert CONTEXT_PREAMBLE in text
        assert "[2024-01-01 to 2024-01-15] Likes pizza" in text

    def test_multiple_results(self) -> None:
        results = [
            _make_result("Likes pizza"),
            _make_result(
                "Learning Python",
                from_date=date(2024, 2, 1),
                to_date=date(2024, 2, 15),
            ),
        ]
        text = format_memory_context(results)
        assert "Likes pizza" in text
        assert "Learning Python" in text


class TestInjectContext:
    def test_appends_to_existing_system_message(self) -> None:
        messages = [
            {"role": "system", "content": "Be helpful"},
            {"role": "user", "content": "Hi"},
        ]
        result = inject_context(messages, "CONTEXT")
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "Be helpful\n\nCONTEXT"
        assert len(result) == 2

    def test_creates_system_message_when_absent(self) -> None:
        messages = [{"role": "user", "content": "Hi"}]
        result = inject_context(messages, "CONTEXT")
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "CONTEXT"
        assert result[1]["role"] == "user"
        assert len(result) == 2

    def test_handles_empty_system_content(self) -> None:
        messages = [
            {"role": "system", "content": ""},
            {"role": "user", "content": "Hi"},
        ]
        result = inject_context(messages, "CONTEXT")
        assert result[0]["content"] == "CONTEXT"

    def test_does_not_mutate_original(self) -> None:
        messages = [
            {"role": "system", "content": "Original"},
            {"role": "user", "content": "Hi"},
        ]
        inject_context(messages, "CONTEXT")
        assert messages[0]["content"] == "Original"


class TestEnrichMessages:
    async def test_enriches_with_results(self) -> None:
        ctx = AsyncMock()
        ctx.search_memories.return_value = [_make_result()]
        messages = [{"role": "user", "content": "What food do I like?"}]

        result = await enrich_messages(messages, ctx, top_k=3)

        ctx.search_memories.assert_awaited_once_with(
            query="What food do I like?", top_k=3
        )
        assert result[0]["role"] == "system"
        assert "Likes pizza" in result[0]["content"]
        assert result[1]["role"] == "user"

    async def test_returns_original_when_no_user_message(self) -> None:
        ctx = AsyncMock()
        messages = [{"role": "system", "content": "Hi"}]

        result = await enrich_messages(messages, ctx)

        ctx.search_memories.assert_not_awaited()
        assert result is messages

    async def test_returns_original_when_no_results(self) -> None:
        ctx = AsyncMock()
        ctx.search_memories.return_value = []
        messages = [{"role": "user", "content": "Hello"}]

        result = await enrich_messages(messages, ctx)

        assert len(result) == 1
        assert result[0]["role"] == "user"

    async def test_returns_original_on_search_error(self) -> None:
        ctx = AsyncMock()
        ctx.search_memories.side_effect = RuntimeError("DB error")
        messages = [{"role": "user", "content": "Hello"}]

        result = await enrich_messages(messages, ctx)

        assert result is messages

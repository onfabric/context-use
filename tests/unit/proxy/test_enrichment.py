from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

from context_use.proxy.enrichment import (
    CONTEXT_PREAMBLE,
    enrich_completion_body,
    enrich_messages,
    enrich_response_body,
    extract_last_user_message,
    extract_last_user_text_from_input,
    format_memory_context,
    inject_context,
    inject_context_into_instructions,
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


class TestEnrichCompletionBody:
    async def test_enriches_messages_in_body(self) -> None:
        ctx = AsyncMock()
        ctx.search_memories.return_value = [_make_result()]
        body = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "What food do I like?"}],
        }

        result = await enrich_completion_body(body, ctx)

        assert result is not body
        assert "Likes pizza" in str(result["messages"][0].get("content", ""))

    async def test_returns_original_when_no_messages(self) -> None:
        ctx = AsyncMock()
        body = {"model": "gpt-4o"}

        result = await enrich_completion_body(body, ctx)

        assert result is body

    async def test_returns_original_when_no_results(self) -> None:
        ctx = AsyncMock()
        ctx.search_memories.return_value = []
        body = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        result = await enrich_completion_body(body, ctx)

        assert result is body

    async def test_does_not_mutate_original(self) -> None:
        ctx = AsyncMock()
        ctx.search_memories.return_value = [_make_result()]
        messages = [{"role": "user", "content": "Hello"}]
        body = {"model": "gpt-4o", "messages": messages}

        await enrich_completion_body(body, ctx)

        assert body["messages"] is messages


class TestExtractLastUserTextFromInput:
    def test_string_input(self) -> None:
        assert extract_last_user_text_from_input("Hello") == "Hello"

    def test_empty_string_returns_none(self) -> None:
        assert extract_last_user_text_from_input("") is None

    def test_array_with_string_content(self) -> None:
        items = [{"role": "user", "content": "What food do I like?"}]
        assert extract_last_user_text_from_input(items) == "What food do I like?"

    def test_array_with_input_text_content(self) -> None:
        items = [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "Describe this"}],
            },
        ]
        assert extract_last_user_text_from_input(items) == "Describe this"

    def test_array_with_text_type_content(self) -> None:
        items = [
            {
                "role": "user",
                "content": [{"type": "text", "text": "Hello there"}],
            },
        ]
        assert extract_last_user_text_from_input(items) == "Hello there"

    def test_picks_last_user_item(self) -> None:
        items = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Reply"},
            {"role": "user", "content": "Second"},
        ]
        assert extract_last_user_text_from_input(items) == "Second"

    def test_skips_non_user_roles(self) -> None:
        items = [
            {"role": "system", "content": "Be helpful"},
            {"role": "developer", "content": "Instructions"},
        ]
        assert extract_last_user_text_from_input(items) is None

    def test_empty_list_returns_none(self) -> None:
        assert extract_last_user_text_from_input([]) is None

    def test_multiple_text_parts(self) -> None:
        items = [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Hello"},
                    {"type": "input_text", "text": "world"},
                ],
            },
        ]
        assert extract_last_user_text_from_input(items) == "Hello world"

    def test_content_list_no_text_parts(self) -> None:
        items = [
            {
                "role": "user",
                "content": [{"type": "input_image", "image_url": "https://..."}],
            },
        ]
        assert extract_last_user_text_from_input(items) is None

    def test_empty_string_content_returns_none(self) -> None:
        items = [{"role": "user", "content": ""}]
        assert extract_last_user_text_from_input(items) is None


class TestInjectContextIntoInstructions:
    def test_appends_to_existing_instructions(self) -> None:
        result = inject_context_into_instructions("Be helpful", "CONTEXT")
        assert result == "Be helpful\n\nCONTEXT"

    def test_returns_context_when_no_instructions(self) -> None:
        result = inject_context_into_instructions(None, "CONTEXT")
        assert result == "CONTEXT"

    def test_returns_context_when_empty_instructions(self) -> None:
        result = inject_context_into_instructions("", "CONTEXT")
        assert result == "CONTEXT"


class TestEnrichResponseBody:
    async def test_enriches_with_string_input(self) -> None:
        ctx = AsyncMock()
        ctx.search_memories.return_value = [_make_result()]
        body = {"model": "gpt-4o", "input": "What food do I like?"}

        result = await enrich_response_body(body, ctx, top_k=3)

        ctx.search_memories.assert_awaited_once_with(
            query="What food do I like?", top_k=3
        )
        assert "Likes pizza" in result["instructions"]

    async def test_enriches_with_array_input(self) -> None:
        ctx = AsyncMock()
        ctx.search_memories.return_value = [_make_result()]
        body = {
            "model": "gpt-4o",
            "input": [{"role": "user", "content": "What food do I like?"}],
        }

        result = await enrich_response_body(body, ctx)

        assert "Likes pizza" in result["instructions"]

    async def test_appends_to_existing_instructions(self) -> None:
        ctx = AsyncMock()
        ctx.search_memories.return_value = [_make_result()]
        body = {
            "model": "gpt-4o",
            "input": "Hello",
            "instructions": "Be helpful",
        }

        result = await enrich_response_body(body, ctx)

        assert result["instructions"].startswith("Be helpful\n\n")
        assert "Likes pizza" in result["instructions"]

    async def test_returns_original_when_no_input(self) -> None:
        ctx = AsyncMock()
        body = {"model": "gpt-4o"}

        result = await enrich_response_body(body, ctx)

        ctx.search_memories.assert_not_awaited()
        assert result is body

    async def test_returns_original_when_no_user_text(self) -> None:
        ctx = AsyncMock()
        body = {
            "model": "gpt-4o",
            "input": [{"role": "system", "content": "Setup"}],
        }

        result = await enrich_response_body(body, ctx)

        ctx.search_memories.assert_not_awaited()
        assert result is body

    async def test_returns_original_when_no_results(self) -> None:
        ctx = AsyncMock()
        ctx.search_memories.return_value = []
        body = {"model": "gpt-4o", "input": "Hello"}

        result = await enrich_response_body(body, ctx)

        assert "instructions" not in result

    async def test_returns_original_on_search_error(self) -> None:
        ctx = AsyncMock()
        ctx.search_memories.side_effect = RuntimeError("DB error")
        body = {"model": "gpt-4o", "input": "Hello"}

        result = await enrich_response_body(body, ctx)

        assert result is body

    async def test_does_not_mutate_original(self) -> None:
        ctx = AsyncMock()
        ctx.search_memories.return_value = [_make_result()]
        body = {"model": "gpt-4o", "input": "Hello"}

        result = await enrich_response_body(body, ctx)

        assert "instructions" not in body
        assert "instructions" in result

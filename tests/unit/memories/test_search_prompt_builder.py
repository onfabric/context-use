from __future__ import annotations

from datetime import UTC, datetime

import pytest

from context_use.memories.prompt.base import GroupContext
from context_use.memories.prompt.search import GoogleSearchMemoryPromptBuilder
from context_use.models.thread import Thread


def _thread(preview: str, dt: datetime) -> Thread:
    return Thread(
        unique_key=preview[:16],
        provider="google",
        interaction_type="google_search",
        payload={},
        version="1.1.0",
        asat=dt,
        content=preview,
    )


def _dt(date_str: str, hour: int = 10) -> datetime:
    return datetime.fromisoformat(f"{date_str}T{hour:02d}:00:00+00:00").replace(
        tzinfo=UTC
    )


@pytest.fixture()
def multi_day_threads() -> list[Thread]:
    return [
        _thread('Searched "python asyncio tutorial" on Google', _dt("2025-01-01", 9)),
        _thread(
            'Searched "asyncio vs threading python" on Google', _dt("2025-01-02", 14)
        ),
        _thread('Visited page "Python asyncio docs" via Google', _dt("2025-01-03", 11)),
    ]


@pytest.fixture()
def group_context(multi_day_threads: list[Thread]) -> GroupContext:
    return GroupContext(
        group_id="test-group-id",
        new_threads=tuple(multi_day_threads),  # type: ignore[arg-type]
    )


def test_build_returns_prompt_item(group_context: GroupContext) -> None:
    item = GoogleSearchMemoryPromptBuilder(group_context).build()
    assert item.item_id == "test-group-id"
    assert item.response_schema is not None
    assert "memories" in item.response_schema.get("properties", {})


def test_prompt_contains_date_range(group_context: GroupContext) -> None:
    item = GoogleSearchMemoryPromptBuilder(group_context).build()
    assert "2025-01-01" in item.prompt
    assert "2025-01-03" in item.prompt


def test_prompt_contains_search_content(
    group_context: GroupContext, multi_day_threads: list[Thread]
) -> None:
    item = GoogleSearchMemoryPromptBuilder(group_context).build()
    for thread in multi_day_threads:
        assert thread.get_content() in item.prompt


def test_searches_grouped_by_day(group_context: GroupContext) -> None:
    item = GoogleSearchMemoryPromptBuilder(group_context).build()
    assert "### 2025-01-01" in item.prompt
    assert "### 2025-01-02" in item.prompt
    assert "### 2025-01-03" in item.prompt


def test_prompt_instructs_multi_day_pattern(group_context: GroupContext) -> None:
    item = GoogleSearchMemoryPromptBuilder(group_context).build()
    assert "multiple" in item.prompt.lower()
    assert "isolated" in item.prompt.lower()


def test_no_asset_uris(group_context: GroupContext) -> None:
    item = GoogleSearchMemoryPromptBuilder(group_context).build()
    assert item.asset_uris == []


def test_single_day_threads_still_build() -> None:
    threads = [
        _thread('Searched "weather london" on Google', _dt("2025-03-10", 8)),
        _thread('Searched "weather paris" on Google', _dt("2025-03-10", 9)),
    ]
    ctx = GroupContext(
        group_id="single-day",
        new_threads=tuple(threads),  # type: ignore[arg-type]
    )
    item = GoogleSearchMemoryPromptBuilder(ctx).build()
    assert "2025-03-10" in item.prompt
    assert "### 2025-03-10" in item.prompt


def test_context_block_injected_when_present(
    multi_day_threads: list[Thread],
) -> None:
    ctx = GroupContext(
        group_id="ctx-test",
        new_threads=tuple(multi_day_threads),  # type: ignore[arg-type]
        user_profile="Alice is a software engineer based in London.",
    )
    item = GoogleSearchMemoryPromptBuilder(ctx).build()
    assert "Alice is a software engineer" in item.prompt

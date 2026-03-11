from __future__ import annotations

from datetime import UTC, datetime

import pytest

from context_use.memories.prompt.activity import (
    ActivityMemoryPromptBuilder,
)
from context_use.memories.prompt.base import GroupContext
from context_use.models.thread import Thread


def _make_thread(
    preview: str,
    asat: datetime,
    *,
    asset_uri: str | None = None,
) -> Thread:
    return Thread(
        unique_key=f"test:{preview[:20]}",
        provider="airbnb",
        interaction_type="airbnb_searches",
        preview=preview,
        payload={},
        version="1",
        asat=asat,
        asset_uri=asset_uri,
    )


DT_DAY1 = datetime(2024, 3, 10, 10, 0, tzinfo=UTC)
DT_DAY1_LATE = datetime(2024, 3, 10, 18, 30, tzinfo=UTC)
DT_DAY2 = datetime(2024, 3, 11, 9, 0, tzinfo=UTC)


class TestHasContent:
    def test_empty_contexts(self) -> None:
        builder = ActivityMemoryPromptBuilder(contexts=[])
        assert not builder.has_content()

    def test_no_threads(self) -> None:
        ctx = GroupContext(group_id="g1", new_threads=[])
        builder = ActivityMemoryPromptBuilder(contexts=[ctx])
        assert not builder.has_content()

    def test_threads_without_assets(self) -> None:
        """Text-only threads should count (unlike MediaMemoryPromptBuilder)."""
        thread = _make_thread("Searched Paris", DT_DAY1)
        ctx = GroupContext(group_id="g1", new_threads=[thread])
        builder = ActivityMemoryPromptBuilder(contexts=[ctx])
        assert builder.has_content()

    def test_threads_with_assets(self) -> None:
        thread = _make_thread("Searched Paris", DT_DAY1, asset_uri="img.jpg")
        ctx = GroupContext(group_id="g1", new_threads=[thread])
        builder = ActivityMemoryPromptBuilder(contexts=[ctx])
        assert builder.has_content()


class TestBuild:
    def test_single_thread_produces_one_prompt(self) -> None:
        thread = _make_thread("Searched Paris (2024-05-01 to 2024-05-05)", DT_DAY1)
        ctx = GroupContext(group_id="g1", new_threads=[thread])
        builder = ActivityMemoryPromptBuilder(contexts=[ctx])

        items = builder.build()

        assert len(items) == 1
        assert items[0].item_id == "g1"
        assert "Paris" in items[0].prompt
        assert "2024-03-10" in items[0].prompt

    def test_empty_group_skipped(self) -> None:
        ctx_empty = GroupContext(group_id="g1", new_threads=[])
        ctx_full = GroupContext(
            group_id="g2",
            new_threads=[_make_thread("Booked 3-night stay", DT_DAY1)],
        )
        builder = ActivityMemoryPromptBuilder(contexts=[ctx_empty, ctx_full])

        items = builder.build()

        assert len(items) == 1
        assert items[0].item_id == "g2"

    def test_no_asset_uris_in_prompt_items(self) -> None:
        thread = _make_thread("Searched Bengaluru", DT_DAY1)
        ctx = GroupContext(group_id="g1", new_threads=[thread])
        builder = ActivityMemoryPromptBuilder(contexts=[ctx])

        items = builder.build()

        assert not items[0].asset_uris

    def test_prompt_contains_activity_log_section(self) -> None:
        thread = _make_thread("Searched Paris", DT_DAY1)
        ctx = GroupContext(group_id="g1", new_threads=[thread])
        builder = ActivityMemoryPromptBuilder(contexts=[ctx])

        items = builder.build()

        assert "## Activity log" in items[0].prompt

    def test_prompt_does_not_reference_images(self) -> None:
        thread = _make_thread("Searched Paris", DT_DAY1)
        ctx = GroupContext(group_id="g1", new_threads=[thread])
        builder = ActivityMemoryPromptBuilder(contexts=[ctx])

        items = builder.build()

        assert "[Image" not in items[0].prompt
        assert "social-media" not in items[0].prompt.lower()

    def test_response_schema_present(self) -> None:
        thread = _make_thread("Searched Paris", DT_DAY1)
        ctx = GroupContext(group_id="g1", new_threads=[thread])
        builder = ActivityMemoryPromptBuilder(contexts=[ctx])

        items = builder.build()

        assert items[0].response_schema is not None
        assert "memories" in items[0].response_schema.get("properties", {})


class TestFormatActivities:
    def test_single_day_no_header(self) -> None:
        threads = [_make_thread("Searched Paris", DT_DAY1)]
        result = ActivityMemoryPromptBuilder._format_activities(threads)

        assert "## Activity log" in result
        assert "### 2024-03-10" not in result
        assert "[10:00] Searched Paris" in result

    def test_multi_day_has_day_headers(self) -> None:
        threads = [
            _make_thread("Searched Paris", DT_DAY1),
            _make_thread("Booked 3-night stay", DT_DAY2),
        ]
        result = ActivityMemoryPromptBuilder._format_activities(threads)

        assert "### 2024-03-10" in result
        assert "### 2024-03-11" in result

    def test_entries_sorted_by_time(self) -> None:
        threads = [
            _make_thread("Evening search", DT_DAY1_LATE),
            _make_thread("Morning search", DT_DAY1),
        ]
        result = ActivityMemoryPromptBuilder._format_activities(threads)

        morning_pos = result.index("Morning search")
        evening_pos = result.index("Evening search")
        assert morning_pos < evening_pos


@pytest.mark.parametrize(
    "preview",
    [
        'Searched "Paris (2024-05-01 to 2024-05-05)" on Airbnb',
        'Saved to "Trips" on Airbnb',
        'Commented "[4/5] Great location" on Airbnb',
        'Saved to "Dream Villas" on Airbnb',
    ],
)
def test_preview_text_preserved_in_prompt(preview: str) -> None:
    thread = _make_thread(preview, DT_DAY1)
    ctx = GroupContext(group_id="g1", new_threads=[thread])
    builder = ActivityMemoryPromptBuilder(contexts=[ctx])

    items = builder.build()

    assert preview in items[0].prompt

from __future__ import annotations

from datetime import date

import pytest

from context_use.eval.metrics import (
    EvalMetrics,
    entity_count,
    score_memories,
    structural_valid,
)
from context_use.memories.prompt.base import Memory
from context_use.models.memory import TapestryMemory


def _mem(content: str, from_date: str = "2024-06-01", to_date: str = "2024-06-01") -> Memory:
    return Memory(content=content, from_date=from_date, to_date=to_date)


class TestEntityCount:
    def test_proper_nouns(self) -> None:
        text = "I met Marco at the Berlin office to discuss Kubernetes."
        count = entity_count(text)
        assert count >= 2

    def test_no_entities(self) -> None:
        text = "had a productive session exploring some ideas"
        assert entity_count(text) == 0

    def test_dates_counted(self) -> None:
        text = "I started the project on 2024-03-15 and finished 2024-04-01."
        count = entity_count(text)
        assert count >= 2

    def test_numbers_with_units(self) -> None:
        text = "I ran 5.2 km this morning and lifted 80 kg at the gym."
        count = entity_count(text)
        assert count >= 2

    def test_urls_counted(self) -> None:
        text = "Check out https://example.com for more details."
        assert entity_count(text) >= 1


class TestStructuralValid:
    def test_valid_memory(self) -> None:
        assert structural_valid(_mem("A real memory about my life."))

    def test_empty_content(self) -> None:
        assert not structural_valid(_mem(""))

    def test_whitespace_only(self) -> None:
        assert not structural_valid(_mem("   "))

    def test_invalid_date(self) -> None:
        assert not structural_valid(_mem("content", from_date="not-a-date"))

    def test_from_after_to(self) -> None:
        assert not structural_valid(_mem("content", from_date="2024-06-10", to_date="2024-06-01"))

    def test_same_day(self) -> None:
        assert structural_valid(_mem("content", from_date="2024-06-01", to_date="2024-06-01"))

    def test_multi_day_range(self) -> None:
        assert structural_valid(_mem("content", from_date="2024-06-01", to_date="2024-06-15"))


class TestScoreMemories:
    def test_empty_list(self) -> None:
        metrics = score_memories([])
        assert metrics.memory_count == 0
        assert metrics.quality_score == 0.0

    def test_single_valid_memory(self) -> None:
        memories = [_mem("I deployed the React app to Vercel on 2024-06-01 with Marco.")]
        metrics = score_memories(memories)
        assert metrics.memory_count == 1
        assert metrics.structural_validity == 1.0
        assert metrics.entity_density > 0

    def test_high_quality_vs_low_quality(self) -> None:
        high_quality = [
            _mem("I debugged the Kubernetes cluster at the Berlin office with Marco on 2024-06-01."),
            _mem("Signed up for the Tokyo Marathon on 2024-10-15 and started training with Nike Run Club."),
            _mem("Migrated our PostgreSQL database from AWS to Google Cloud Platform for 45 USD/month."),
        ]
        low_quality = [
            _mem("had a productive session"),
            _mem("explored some ideas today"),
            _mem("worked on stuff"),
        ]
        high_metrics = score_memories(high_quality)
        low_metrics = score_memories(low_quality)
        assert high_metrics.quality_score > low_metrics.quality_score
        assert high_metrics.entity_density > low_metrics.entity_density

    def test_invalid_memories_lower_score(self) -> None:
        valid = [_mem("I visited Paris with Sarah.")]
        invalid = [_mem("", from_date="bad-date")]
        assert score_memories(valid).quality_score > score_memories(invalid).quality_score

    def test_metrics_are_frozen(self) -> None:
        metrics = score_memories([_mem("test")])
        with pytest.raises(AttributeError):
            metrics.memory_count = 99  # type: ignore[misc]

    def test_scores_tapestry_memories(self) -> None:
        memories: list[TapestryMemory] = [
            TapestryMemory(
                content="I debugged a Kubernetes issue at the Berlin office.",
                from_date=date(2024, 6, 1),
                to_date=date(2024, 6, 1),
                group_id="g1",
            ),
            TapestryMemory(
                content="Signed up for the Tokyo Marathon.",
                from_date=date(2024, 10, 1),
                to_date=date(2024, 10, 1),
                group_id="g1",
            ),
        ]
        metrics = score_memories(memories)  # type: ignore[arg-type]
        assert metrics.memory_count == 2
        assert metrics.structural_validity == 1.0
        assert metrics.entity_density > 0

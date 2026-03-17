from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from statistics import mean, median
from typing import Protocol, runtime_checkable


@runtime_checkable
class Scorable(Protocol):
    @property
    def content(self) -> str: ...
    @property
    def from_date(self) -> str | date: ...
    @property
    def to_date(self) -> str | date: ...


_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?(?:\s*(?:km|kg|lb|mi|hrs?|mins?|%|USD|EUR|GBP))\b", re.IGNORECASE)
_PROPER_NOUN_RE = re.compile(r"(?<!\. )(?<!\.\n)(?<!^)(?<!\n)\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")
_URL_RE = re.compile(r"https?://\S+")


def entity_count(text: str) -> int:
    dates = len(_DATE_RE.findall(text))
    numbers = len(_NUMBER_RE.findall(text))
    proper_nouns = len(_PROPER_NOUN_RE.findall(text))
    urls = len(_URL_RE.findall(text))
    return dates + numbers + proper_nouns + urls


def structural_valid(memory: Scorable) -> bool:
    if not memory.content or not memory.content.strip():
        return False
    try:
        from_dt = memory.from_date if isinstance(memory.from_date, date) else date.fromisoformat(memory.from_date)
        to_dt = memory.to_date if isinstance(memory.to_date, date) else date.fromisoformat(memory.to_date)
    except ValueError:
        return False
    return from_dt <= to_dt


_MIN_CONTENT_LENGTH = 30
_MAX_CONTENT_LENGTH = 400


def _length_ok(content: str) -> bool:
    return _MIN_CONTENT_LENGTH <= len(content) <= _MAX_CONTENT_LENGTH


@dataclass(frozen=True)
class EvalMetrics:
    memory_count: int
    structural_validity: float
    length_ok_ratio: float
    entity_density: float
    avg_content_length: float
    median_content_length: float
    quality_score: float


def score_memories(memories: Sequence[Scorable]) -> EvalMetrics:
    if not memories:
        return EvalMetrics(
            memory_count=0,
            structural_validity=0.0,
            length_ok_ratio=0.0,
            entity_density=0.0,
            avg_content_length=0.0,
            median_content_length=0.0,
            quality_score=0.0,
        )

    valid_count = sum(1 for m in memories if structural_valid(m))
    structural_validity = valid_count / len(memories)

    lengths = [len(m.content) for m in memories]
    avg_length = mean(lengths)
    med_length = median(lengths)

    length_ok = sum(1 for m in memories if _length_ok(m.content)) / len(memories)

    entity_counts = [entity_count(m.content) for m in memories]
    entity_density = mean(entity_counts) if entity_counts else 0.0

    quality_score = (
        0.5 * structural_validity
        + 0.5 * length_ok
    )

    return EvalMetrics(
        memory_count=len(memories),
        structural_validity=structural_validity,
        length_ok_ratio=length_ok,
        entity_density=entity_density,
        avg_content_length=avg_length,
        median_content_length=med_length,
        quality_score=quality_score,
    )

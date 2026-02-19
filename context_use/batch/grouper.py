from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, timedelta

from context_use.etl.models.thread import Thread


@dataclass(frozen=True)
class WindowConfig:
    """Controls the sliding-window used to group interactions into prompts."""

    window_days: int = 5
    overlap_days: int = 1
    max_memories: int | None = None
    min_memories: int | None = None

    def __post_init__(self) -> None:
        if self.overlap_days >= self.window_days:
            raise ValueError("overlap_days must be smaller than window_days")

    @property
    def step_days(self) -> int:
        return self.window_days - self.overlap_days

    @property
    def effective_max_memories(self) -> int:
        if self.max_memories is not None:
            return self.max_memories
        return max(5, self.window_days * 3)

    @property
    def effective_min_memories(self) -> int:
        if self.min_memories is not None:
            return self.min_memories
        return max(1, self.window_days)


def encode_window_key(from_date: date, to_date: date) -> str:
    return f"{from_date.isoformat()}/{to_date.isoformat()}"


def decode_window_key(key: str) -> tuple[date, date]:
    from_str, to_str = key.split("/")
    return date.fromisoformat(from_str), date.fromisoformat(to_str)


@dataclass
class ThreadGroup:
    """A set of threads that must be processed together as one LLM prompt."""

    group_key: str
    threads: list[Thread] = field(default_factory=list)


class ThreadGrouper(ABC):
    """Strategy for partitioning threads into atomic groups."""

    @abstractmethod
    def group(self, threads: list[Thread]) -> list[ThreadGroup]:
        """Partition *threads* into groups that must be processed together."""
        ...


class WindowGrouper(ThreadGrouper):
    """Groups threads into overlapping time windows."""

    def __init__(self, config: WindowConfig | None = None) -> None:
        self.config = config or WindowConfig()

    def group(self, threads: list[Thread]) -> list[ThreadGroup]:
        if not threads:
            return []

        sorted_threads = sorted(threads, key=lambda t: t.asat)
        min_date = sorted_threads[0].asat.date()
        max_date = sorted_threads[-1].asat.date()

        groups: list[ThreadGroup] = []
        window_start = min_date

        while window_start <= max_date:
            window_end = window_start + timedelta(days=self.config.window_days - 1)
            window_threads = [
                t for t in sorted_threads if window_start <= t.asat.date() <= window_end
            ]
            if window_threads:
                groups.append(
                    ThreadGroup(
                        group_key=encode_window_key(window_start, window_end),
                        threads=window_threads,
                    )
                )
            window_start += timedelta(days=self.config.step_days)

        return groups

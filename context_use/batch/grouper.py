from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import cast

from context_use.models.thread import NonEmptyThreads, Thread
from context_use.models.utils import generate_uuidv4


@dataclass(frozen=True)
class WindowConfig:
    """Controls the sliding-window used to group interactions into prompts."""

    window_days: int = 5
    overlap_days: int = 1

    def __post_init__(self) -> None:
        if self.overlap_days >= self.window_days:
            raise ValueError("overlap_days must be smaller than window_days")

    @property
    def step_days(self) -> int:
        return self.window_days - self.overlap_days


@dataclass(init=False)
class ThreadGroup:
    """A set of threads that must be processed together as one LLM prompt."""

    threads: NonEmptyThreads
    group_id: str

    @staticmethod
    def _as_non_empty_threads(threads: Iterable[Thread]) -> NonEmptyThreads:
        t = tuple(threads)
        if len(t) < 1:
            raise ValueError("ThreadGroup requires at least one thread")
        return cast(NonEmptyThreads, t)

    def __init__(self, threads: Iterable[Thread], group_id: str | None = None) -> None:
        self.threads = ThreadGroup._as_non_empty_threads(threads)
        self.group_id = group_id if group_id is not None else generate_uuidv4()


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
                groups.append(ThreadGroup(threads=window_threads))
            window_start += timedelta(days=self.config.step_days)

        return groups


class CollectionGrouper(ThreadGrouper):
    """Groups threads by their collection ID."""

    def group(self, threads: list[Thread]) -> list[ThreadGroup]:
        if not threads:
            return []

        buckets: dict[str, list[Thread]] = defaultdict(list)
        for t in threads:
            cid = t.get_collection()
            if cid:
                buckets[cid].append(t)

        return [
            ThreadGroup(threads=sorted(ts, key=lambda t: t.asat))
            for ts in buckets.values()
        ]

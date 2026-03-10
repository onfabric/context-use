from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from context_use.batch.manager import ScheduleInstruction
from context_use.cli import output as out
from context_use.cli.base import run_batches
from context_use.models.batch import Batch

type SpinnerEvent = tuple[str, str, int | None, bool]


@dataclass
class _SpinnerSink:
    created_with: list[tuple[str, str]] = field(default_factory=list)
    events: list[SpinnerEvent] = field(default_factory=list)
    ticks: int = 0


@dataclass
class _FakeClock:
    now: float = 0.0

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


class _FakeContext:
    def __init__(
        self,
        scripts: dict[str, list[ScheduleInstruction]],
        statuses: dict[str, list[str]],
    ) -> None:
        self.scripts = scripts
        self.statuses = statuses
        self.current_status = {batch_id: "CREATED" for batch_id in scripts}
        self.calls: list[str] = []

    async def advance_batch(self, batch_id: str) -> ScheduleInstruction:
        self.calls.append(batch_id)
        queue = self.scripts[batch_id]
        if not queue:
            raise AssertionError(f"No scheduled instruction left for {batch_id}")
        status_queue = self.statuses[batch_id]
        if not status_queue:
            raise AssertionError(f"No status left for {batch_id}")
        self.current_status[batch_id] = status_queue.pop(0)
        return queue.pop(0)

    async def get_batch_status(self, batch_id: str) -> str | None:
        return self.current_status.get(batch_id)


class _RecorderSpinner:
    def __init__(self, batches: list[tuple[str, str]], sink: _SpinnerSink) -> None:
        self.batches = batches
        self.sink = sink

    def __enter__(self) -> _RecorderSpinner:
        self.sink.created_with = self.batches
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    def update(
        self,
        batch_id: str,
        status: str,
        *,
        countdown_seconds: int | None = None,
        done: bool = False,
    ) -> None:
        self.sink.events.append((batch_id, status, countdown_seconds, done))

    def tick(self) -> None:
        self.sink.ticks += 1


def _make_batch(batch_id: str, batch_number: int) -> Batch:
    return Batch(
        id=batch_id,
        batch_number=batch_number,
        category="memories",
        states=[{"status": "CREATED"}],
    )


async def test_run_batches_skips_countdown_when_requested(monkeypatch) -> None:
    clock = _FakeClock()
    spinner_sink = _SpinnerSink()

    monkeypatch.setattr("context_use.cli.base.time.monotonic", clock.monotonic)
    monkeypatch.setattr("context_use.cli.base.asyncio.sleep", clock.sleep)
    monkeypatch.setattr(
        "context_use.cli.base.out.BatchStatusSpinner",
        lambda batches: _RecorderSpinner(batches, spinner_sink),
    )

    b1 = _make_batch("batch-1", 1)
    b2 = _make_batch("batch-2", 2)
    ctx = _FakeContext(
        scripts={
            "batch-1": [
                ScheduleInstruction(
                    stop=False,
                    countdown=7,
                ),
                ScheduleInstruction(stop=True),
            ],
            "batch-2": [ScheduleInstruction(stop=True)],
        },
        statuses={
            "batch-1": ["MEMORY_GENERATE_PENDING", "COMPLETE"],
            "batch-2": ["FAILED"],
        },
    )

    await run_batches(cast(Any, ctx), [b1, b2], skip_countdown=True)

    assert ctx.calls == ["batch-1", "batch-2", "batch-1"]
    assert clock.now == 0.0
    assert ("batch-1", "MEMORY_GENERATE_PENDING", 0, False) in spinner_sink.events
    assert ("batch-1", "COMPLETE", None, True) in spinner_sink.events
    assert ("batch-2", "FAILED", None, True) in spinner_sink.events
    assert spinner_sink.ticks >= 1


async def test_run_batches_waits_for_countdown_by_default(monkeypatch) -> None:
    clock = _FakeClock()
    spinner_sink = _SpinnerSink()

    monkeypatch.setattr("context_use.cli.base.time.monotonic", clock.monotonic)
    monkeypatch.setattr("context_use.cli.base.asyncio.sleep", clock.sleep)
    monkeypatch.setattr(
        "context_use.cli.base.out.BatchStatusSpinner",
        lambda batches: _RecorderSpinner(batches, spinner_sink),
    )

    batch = _make_batch("batch-1", 1)
    ctx = _FakeContext(
        scripts={
            "batch-1": [
                ScheduleInstruction(
                    stop=False,
                    countdown=3,
                ),
                ScheduleInstruction(stop=True),
            ]
        },
        statuses={"batch-1": ["MEMORY_EMBED_PENDING", "COMPLETE"]},
    )

    await run_batches(cast(Any, ctx), [batch])

    assert ctx.calls == ["batch-1", "batch-1"]
    assert clock.now >= 3.0
    assert ("batch-1", "MEMORY_EMBED_PENDING", 3, False) in spinner_sink.events
    assert ("batch-1", "COMPLETE", None, True) in spinner_sink.events


def test_batch_spinner_non_tty_prints_terminal_rows(monkeypatch, capsys) -> None:
    monkeypatch.setattr(out, "_IS_TTY", False)

    with out.BatchStatusSpinner([("batch-1", "Batch 001")]) as spinner:
        spinner.update("batch-1", "MEMORY_GENERATE_PENDING", countdown_seconds=2)
        spinner.update("batch-1", "COMPLETE", done=True)

    captured = capsys.readouterr().out
    assert "Batch 001" in captured
    assert "Complete" in captured

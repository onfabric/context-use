from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from types import TracebackType

from context_use.memories.states import MemoryBatchStatus


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()


_COLOR = _supports_color()
_IS_TTY = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _ansi(code: str, text: str) -> str:
    if not _COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(text: str) -> str:
    return _ansi("1", text)


def dim(text: str) -> str:
    return _ansi("2", text)


def green(text: str) -> str:
    return _ansi("32", text)


def yellow(text: str) -> str:
    return _ansi("33", text)


def red(text: str) -> str:
    return _ansi("31", text)


def cyan(text: str) -> str:
    return _ansi("36", text)


# ── Structured output ───────────────────────────────────────────────


def header(title: str) -> None:
    """Print a section header."""
    print(f"\n{bold(title)}")


def success(msg: str) -> None:
    print(f"  {green('✓')} {msg}")


def warn(msg: str) -> None:
    print(f"  {yellow('!')} {msg}")


def error(msg: str) -> None:
    print(f"  {red('✗')} {msg}")


def info(msg: str) -> None:
    print(f"  {msg}")


def kv(key: str, value: object, indent: int = 2) -> None:
    """Print a key-value pair."""
    pad = " " * indent
    print(f"{pad}{dim(str(key) + ':')}  {value}")


def rule() -> None:
    """Print a horizontal rule."""
    width = min(os.get_terminal_size().columns, 60) if sys.stdout.isatty() else 60
    print(dim("─" * width))


def next_step(command: str, description: str = "") -> None:
    """Print a suggested next-step command."""
    desc = f"  {dim(description)}" if description else ""
    print(f"    {cyan(command)}{desc}")


def banner() -> None:
    """Print the opening banner."""
    print(bold("context-use") + dim(" — turn your data exports into AI memory"))


@dataclass
class _BatchLine:
    status: str = MemoryBatchStatus.created.value
    countdown_seconds: int | None = None
    done: bool = False


class BatchStatusSpinner:
    """Docker-like per-batch spinner with live in-place updates."""

    _FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
    _LABEL_WIDTH = 12
    _STATUS_WIDTH = 20
    _STATUS_LABELS = {
        MemoryBatchStatus.created: "Waiting",
        MemoryBatchStatus.memory_generate_pending: "Generating",
        MemoryBatchStatus.memory_generate_complete: "Generated",
        MemoryBatchStatus.memory_embed_pending: "Embedding",
        MemoryBatchStatus.memory_embed_complete: "Embedded",
        MemoryBatchStatus.complete: "Complete",
        MemoryBatchStatus.skipped: "Skipped",
        MemoryBatchStatus.failed: "Failed",
    }

    def __init__(self, batches: list[tuple[str, str]]) -> None:
        self._order = [batch_id for batch_id, _ in batches]
        self._labels = {batch_id: label for batch_id, label in batches}
        self._lines = {batch_id: _BatchLine() for batch_id in self._order}
        self._frame_index = 0
        self._rendered_lines = 0
        self._printed_terminal: set[str] = set()

    def __enter__(self) -> BatchStatusSpinner:
        self._render(force=True)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if _IS_TTY and self._rendered_lines:
            sys.stdout.write("\n")
            sys.stdout.flush()

    def update(
        self,
        batch_id: str,
        status: str,
        *,
        countdown_seconds: int | None = None,
        done: bool = False,
    ) -> None:
        self._lines[batch_id] = _BatchLine(
            status=status,
            countdown_seconds=countdown_seconds if not done else None,
            done=done,
        )
        self._render(force=done)

    def tick(self) -> None:
        self._frame_index = (self._frame_index + 1) % len(self._FRAMES)
        self._render(force=False)

    def _render(self, *, force: bool) -> None:
        if not _IS_TTY:
            if not force:
                return
            for batch_id in self._order:
                line = self._lines[batch_id]
                if not line.done or batch_id in self._printed_terminal:
                    continue
                self._printed_terminal.add(batch_id)
                icon = self._terminal_icon_for(line.status)
                label = self._labels[batch_id]
                status_text = self._status_text(line.status)
                print(f"  {icon} {label} {status_text}")
            return

        if self._rendered_lines:
            sys.stdout.write(f"\x1b[{self._rendered_lines}F")

        frame = self._FRAMES[self._frame_index]
        for batch_id in self._order:
            line = self._lines[batch_id]
            symbol = self._symbol_for(line, frame)
            label = self._labels[batch_id].ljust(self._LABEL_WIDTH)
            status_text = self._status_text(line.status).ljust(self._STATUS_WIDTH)
            detail = self._detail_text(line)
            sys.stdout.write(f"\x1b[2K  {symbol} {label} {status_text}{detail}\n")

        self._rendered_lines = len(self._order)
        sys.stdout.flush()

    def _symbol_for(self, line: _BatchLine, frame: str) -> str:
        if not line.done:
            return cyan(frame)
        return self._terminal_icon_for(line.status)

    def _terminal_icon_for(self, status: str) -> str:
        parsed = MemoryBatchStatus.parse(status)
        if parsed == MemoryBatchStatus.failed:
            return red("✗")
        if parsed == MemoryBatchStatus.skipped:
            return yellow("!")
        return green("✓")

    def _status_text(self, status: str) -> str:
        parsed = MemoryBatchStatus.parse(status)
        if parsed is None:
            return status.replace("_", " ").title()
        return self._STATUS_LABELS[parsed]

    def _detail_text(self, line: _BatchLine) -> str:
        if line.done:
            return ""
        if line.countdown_seconds is None:
            return dim("  (working)")
        if line.countdown_seconds <= 0:
            return dim("  (up next)")
        return dim(f"  (next in {line.countdown_seconds}s)")

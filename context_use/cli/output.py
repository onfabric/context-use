from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from types import TracebackType

from rich.console import Console
from rich.status import Status


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
    status: str = "CREATED"
    countdown_seconds: int | None = None
    done: bool = False


class BatchStatusSpinner:
    """Per-batch status UI backed by Rich's status spinner."""

    def __init__(self, batches: list[tuple[str, str]]) -> None:
        self._order = [batch_id for batch_id, _ in batches]
        self._labels = {batch_id: label for batch_id, label in batches}
        self._lines = {batch_id: _BatchLine() for batch_id in self._order}
        self._console = Console()
        self._status: Status | None = None
        self._printed_terminal: set[str] = set()

    def __enter__(self) -> BatchStatusSpinner:
        if _IS_TTY:
            self._status = self._console.status(
                self._render_status_text(),
                spinner="dots",
            )
            self._status.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._status is not None:
            self._status.__exit__(exc_type, exc_val, exc_tb)
            self._status = None

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
        if _IS_TTY and self._status is not None:
            self._status.update(self._render_status_text())
        elif done and batch_id not in self._printed_terminal:
            self._printed_terminal.add(batch_id)
            icon = self._terminal_icon_for(status)
            label = self._labels[batch_id]
            print(f"  {icon} {label} {self._status_text(status)}")

    def tick(self) -> None:
        if _IS_TTY and self._status is not None:
            self._status.update(self._render_status_text())

    def _render_status_text(self) -> str:
        parts = []
        for batch_id in self._order:
            line = self._lines[batch_id]
            label = self._labels[batch_id]
            status = self._status_text(line.status)
            detail = self._detail_text(line)
            if detail:
                parts.append(f"{label}: {status} ({detail})")
            else:
                parts.append(f"{label}: {status}")
        return " | ".join(parts)

    def _terminal_icon_for(self, status: str) -> str:
        if status == "FAILED":
            return red("✗")
        if status == "SKIPPED":
            return yellow("!")
        return green("✓")

    def _status_text(self, status: str) -> str:
        return status.replace("_", " ").title()

    def _detail_text(self, line: _BatchLine) -> str | None:
        if line.done:
            return None
        if line.countdown_seconds is None:
            return "working"
        if line.countdown_seconds <= 0:
            return "up next"
        return f"next in {line.countdown_seconds}s"

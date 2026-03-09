from __future__ import annotations

import os
import sys
from types import TracebackType


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


class ProgressBar:
    """Multi-phase in-place terminal progress bar.

    Each call to ``update(label, completed, total)`` redraws the current line.
    When the label changes the previous line is finalised and a new phase
    starts on the next line::

        Generating  ██████████████████████████████  100%  5/5
        Embedding   ████████████████░░░░░░░░░░░░░░   57%  4/7
    """

    _BAR_WIDTH = 30
    _LABEL_WIDTH = 12

    def __init__(self) -> None:
        self._current_label = ""

    def __enter__(self) -> ProgressBar:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if _IS_TTY and self._current_label:
            sys.stdout.write("\n")
            sys.stdout.flush()

    def update(self, label: str, completed: int, total: int) -> None:
        if label != self._current_label:
            if _IS_TTY and self._current_label:
                sys.stdout.write("\n")
            self._current_label = label
        total = max(total, 1)
        frac = completed / total
        filled = int(self._BAR_WIDTH * frac)
        bar = bold("█" * filled) + dim("░" * (self._BAR_WIDTH - filled))
        pct = f"{frac * 100:3.0f}%"
        counter = f"{completed}/{total}"
        padded = label.ljust(self._LABEL_WIDTH)
        line = f"  {padded}{bar}  {pct}  {dim(counter)}"
        if _IS_TTY:
            sys.stdout.write(f"\r{line}")
            sys.stdout.flush()
        elif completed == total:
            print(line)

"""Terminal output helpers for the context-use CLI.

Provides simple, dependency-free formatting with ANSI colors.
Automatically disables color when stdout is not a TTY or when
the ``NO_COLOR`` environment variable is set.
"""

from __future__ import annotations

import os
import sys


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()


_COLOR = _supports_color()


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

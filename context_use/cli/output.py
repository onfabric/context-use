import os
import sys
from dataclasses import dataclass
from types import TracebackType

from rich.console import Console, RenderableType
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text


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


@dataclass
class _BatchLine:
    status: str = "CREATED"
    countdown_seconds: int | None = None
    done: bool = False


class BatchStatusSpinner:
    """Per-batch status UI backed by Rich live rendering."""

    _LABEL_WIDTH = 12
    _STATUS_WIDTH = 28

    def __init__(self, batches: list[tuple[str, str]]) -> None:
        self._order = [batch_id for batch_id, _ in batches]
        self._labels = {batch_id: label for batch_id, label in batches}
        self._lines = {batch_id: _BatchLine() for batch_id in self._order}
        self._console = Console()
        self._live: Live | None = None

    def __enter__(self) -> "BatchStatusSpinner":
        self._live = Live(
            self._render_table(),
            console=self._console,
            refresh_per_second=12,
            transient=False,
        )
        self._live.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._live is not None:
            self._live.__exit__(exc_type, exc_val, exc_tb)
            self._live = None

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
        self._refresh()

    def tick(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._render_table(), refresh=True)

    def _render_table(self) -> Table:
        table = Table.grid(padding=(0, 1), expand=True)
        table.add_column(width=2, no_wrap=True)
        table.add_column(width=self._LABEL_WIDTH, no_wrap=True)
        table.add_column(width=self._STATUS_WIDTH)
        table.add_column(ratio=1)

        for batch_id in self._order:
            line = self._lines[batch_id]
            table.add_row(
                self._indicator(line),
                self._labels[batch_id],
                self._status_text(line.status),
                self._detail_text(line),
            )
        return table

    def _indicator(self, line: _BatchLine) -> RenderableType:
        if line.done:
            return self._terminal_icon_for(line.status)
        return Spinner("dots")

    def _terminal_icon_for(self, status: str) -> Text:
        if status == "FAILED":
            return Text("✗", style="red")
        if status == "SKIPPED":
            return Text("!", style="yellow")
        return Text("✓", style="green")

    def _status_text(self, status: str) -> str:
        return status.replace("_", " ").title()

    def _detail_text(self, line: _BatchLine) -> str:
        if line.done:
            return ""
        if line.countdown_seconds is None:
            return "working"
        if line.countdown_seconds <= 0:
            return "up next"
        return f"next in {line.countdown_seconds}s"

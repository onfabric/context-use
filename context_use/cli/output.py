import os
import sys
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING

from rich.console import Console, RenderableType
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from context_use.batch.states import StopState

if TYPE_CHECKING:
    from context_use.batch.states import State


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
    state: State
    detail: str = ""


class BatchStatusSpinner:
    """Per-batch status UI backed by Rich live rendering."""

    _LABEL_WIDTH = 12
    _STATUS_WIDTH = 28
    _STATUS_STYLES = {
        "CREATED": "cyan",
        "MEMORY_GENERATE_PENDING": "bright_cyan",
        "MEMORY_GENERATE_COMPLETE": "spring_green3",
        "MEMORY_EMBED_PENDING": "green3",
        "MEMORY_EMBED_COMPLETE": "green",
        "COMPLETE": "bold green",
        "SKIPPED": "yellow",
        "FAILED": "red",
    }

    def __init__(self, batches: list[tuple[str, str, State, str]]) -> None:
        self._order = [batch_id for batch_id, _, _, _ in batches]
        self._labels = {batch_id: label for batch_id, label, _, _ in batches}
        self._lines = {
            batch_id: _BatchLine(state=state, detail=detail)
            for batch_id, _, state, detail in batches
        }
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
            self._console.print("")

    def update(
        self,
        batch_id: str,
        state: State,
        *,
        detail: str = "",
    ) -> None:
        new_line = _BatchLine(
            state=state,
            detail=detail,
        )
        if self._lines.get(batch_id) == new_line:
            return
        self._lines[batch_id] = new_line
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
                self._status_text(line.state),
                Text(line.detail, style="dim") if line.detail else Text(""),
            )
        return table

    def _indicator(self, line: _BatchLine) -> RenderableType:
        if isinstance(line.state, StopState):
            return self._terminal_icon_for(line.state)
        return Spinner("dots", style="cyan")

    def _terminal_icon_for(self, state: State) -> Text:
        if state.status == "FAILED":
            return Text("✗", style="red")
        if state.status == "SKIPPED":
            return Text("!", style="yellow")
        return Text("✓", style="green")

    def _status_text(self, state: State) -> Text:
        return Text(
            state.status.replace("_", " ").title(),
            style=self._status_style(state.status),
        )

    def _status_style(self, status: str) -> str:
        return self._STATUS_STYLES.get(status, "bright_blue")

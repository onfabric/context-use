from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from types import TracebackType

from rich.console import Console, RenderableType
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from context_use.batch.states import State, StopState


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
class _Row:
    label: str
    state: State
    detail: str = ""


class BatchStatusSpinner:
    _STATUS_STYLES: dict[str, str] = {
        "CREATED": "cyan",
        "COMPLETE": "bold green",
        "SKIPPED": "yellow",
        "FAILED": "red",
    }

    def __init__(
        self,
        batches: list[tuple[str, str, State, str]],
    ) -> None:
        self._rows: dict[str, _Row] = {}
        for batch_id, label, state, detail in batches:
            self._rows[batch_id] = _Row(label=label, state=state, detail=detail)
        self._console = Console()
        self._live: Live | None = None

    def __enter__(self) -> BatchStatusSpinner:
        self._live = Live(
            self._render(),
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

    @property
    def pending_ids(self) -> set[str]:
        return {
            batch_id
            for batch_id, row in self._rows.items()
            if not isinstance(row.state, StopState)
        }

    def update(self, batch_id: str, state: State, *, detail: str = "") -> None:
        row = self._rows.get(batch_id)
        if row is None:
            return
        effective_detail = detail or row.detail
        if row.state == state and row.detail == effective_detail:
            return
        row.state = state
        row.detail = effective_detail
        if self._live is not None:
            self._live.update(self._render(), refresh=True)

    def _render(self) -> Table:
        table = Table.grid(padding=(0, 1), expand=True)
        table.add_column(width=2, no_wrap=True)
        table.add_column(width=12, no_wrap=True)
        table.add_column(width=28)
        table.add_column(ratio=1)

        for row in self._rows.values():
            table.add_row(
                self._indicator(row.state),
                row.label,
                self._status_text(row.state.status),
                Text(row.detail, style="dim") if row.detail else Text(""),
            )
        return table

    @staticmethod
    def _indicator(state: State) -> RenderableType:
        if not isinstance(state, StopState):
            return Spinner("dots", style="cyan")
        if state.status == "FAILED":
            return Text("✗", style="red")
        if state.status == "SKIPPED":
            return Text("!", style="yellow")
        return Text("✓", style="green")

    def _status_text(self, status: str) -> Text:
        style = self._STATUS_STYLES.get(status, "bright_blue")
        return Text(status.replace("_", " ").title(), style=style)

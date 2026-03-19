from __future__ import annotations

import logging
import sys
import textwrap
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from context_use.store.base import MemorySearchResult

_PREVIEW_LEN = 40

_console = Console(stderr=True)


def _short_id(full_id: str, length: int = 5) -> str:
    if len(full_id) <= length:
        return full_id
    return f"{full_id[:length]}…"


def log_request(
    method: str,
    path: str,
    *,
    model: str | None = None,
    session_id: str | None = None,
    stream: bool = False,
) -> None:
    parts = [f"[cyan]→ {method} {path}[/cyan]"]
    if model:
        parts.append(f"model={model}")
    if session_id:
        parts.append(f"[dim]session={_short_id(session_id)}[/dim]")
    if stream:
        parts.append("stream")
    _console.print()
    _console.print("  ".join(parts), highlight=False)


def log_enrichment(results: list[MemorySearchResult]) -> None:
    _console.print(f"  [green]✦ {len(results)} memories:[/green]", highlight=False)
    for r in results:
        preview = (
            f"{r.content[:_PREVIEW_LEN]}…"
            if len(r.content) > _PREVIEW_LEN
            else r.content
        )
        _console.print(
            f"    · {_short_id(r.id)}  [dim]{preview}[/dim]", highlight=False
        )


def log_response(status: int, *, chunks: int | None = None) -> None:
    style = "green" if status < 400 else "red"
    status_text = f"{status} OK" if status < 400 else str(status)
    parts = [f"  [{style}]← {status_text}[/{style}]"]
    if chunks is not None:
        parts.append(f"[dim]{chunks} chunks[/dim]")
    _console.print("  ".join(parts), highlight=False)


def log_processing_start() -> None:
    _console.print("  [dim]⚙ Processing…[/dim]", highlight=False)


def log_generation_done(new_count: int, total: int, summary: str) -> None:
    _console.print(
        f"  ⚙ Done: {new_count:+d} memories (total {total})", highlight=False
    )
    stripped = summary.strip()
    if stripped:
        _console.print(
            f"[dim]{textwrap.indent(stripped, '    ')}[/dim]", highlight=False
        )


def log_tool_action(
    verb: str,
    memory_id: str | None = None,
    *,
    count: int | None = None,
) -> None:
    parts = [f"    · {verb}"]
    if memory_id:
        parts.append(_short_id(memory_id))
    if count is not None:
        parts.append(f"{count} memories")
    _console.print(" ".join(parts), highlight=False)


def setup_proxy_logging() -> None:
    ctx_logger = logging.getLogger("context_use")
    ctx_logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    ctx_logger.addHandler(handler)

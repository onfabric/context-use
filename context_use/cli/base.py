from __future__ import annotations

import argparse
import asyncio
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from context_use.cli import output as out
from context_use.config import Config, build_ctx, load_config

if TYPE_CHECKING:
    from context_use import ContextUse
    from context_use.facade.types import PipelineResult
    from context_use.models.batch import Batch


# ── Infrastructure helpers ────────────────────────────────────────────────────


async def run_batches(
    ctx: ContextUse,
    batches: list[Batch],
    *,
    skip_countdown: bool = False,
) -> None:
    """Drive all batches to completion, polling until each stops."""
    from context_use.batch.manager import ScheduleInstruction

    if not batches:
        return

    ordered_ids = [batch.id for batch in batches]
    pending: set[str] = set(ordered_ids)
    next_due: dict[str, float] = {batch_id: 0.0 for batch_id in ordered_ids}
    last_status: dict[str, str] = {batch.id: batch.current_status for batch in batches}
    batch_labels = [(batch.id, f"Batch {batch.batch_number:03d}") for batch in batches]

    with out.BatchStatusSpinner(batch_labels) as spinner:
        while pending:
            now = time.monotonic()
            advanced = False

            for batch_id in ordered_ids:
                if batch_id not in pending:
                    continue

                due_at = next_due[batch_id]
                if now < due_at:
                    remaining = max(0, int(due_at - now + 0.999))
                    spinner.update(
                        batch_id,
                        last_status[batch_id],
                        countdown_seconds=remaining,
                    )
                    continue

                instruction: ScheduleInstruction = await ctx.advance_batch(batch_id)
                status = instruction.status or last_status[batch_id]
                last_status[batch_id] = status
                advanced = True

                if instruction.stop:
                    spinner.update(batch_id, status, done=True)
                    pending.remove(batch_id)
                    continue

                countdown = 0 if skip_countdown else (instruction.countdown or 0)
                next_due[batch_id] = time.monotonic() + countdown
                spinner.update(batch_id, status, countdown_seconds=countdown)

            if pending:
                spinner.tick()
                await asyncio.sleep(0 if advanced else 0.1)


def providers() -> list[str]:
    """Return the list of registered provider names."""
    from context_use.providers.registry import list_providers

    return list_providers()


# ── Guard functions ───────────────────────────────────────────────────────────


def require_api_key(cfg: Config) -> None:
    """Exit with guidance if no API key is configured (no interactive prompt)."""
    if cfg.openai_api_key:
        return
    out.error(
        "OpenAI API key not configured. "
        "Run 'context-use config set-key' or set OPENAI_API_KEY."
    )
    sys.exit(1)


# ── Archive-picker helpers ────────────────────────────────────────────────────


def _scan_input_dir(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        return []
    return sorted(input_dir.glob("*.zip"), key=lambda p: p.name)


def _guess_provider(filename: str) -> str | None:
    name = filename.lower()
    for p in providers():
        if p in name:
            return p
    return None


def pick_archive_interactive(cfg: Config) -> tuple[str, str] | None:
    """Interactive picker: list archives in data/input and let user choose.

    Returns ``(provider_str, zip_path)`` or ``None`` if the user aborts.
    """
    cfg.ensure_dirs()
    archives = _scan_input_dir(cfg.input_dir)
    provider_list = providers()

    if not archives:
        out.warn(f"No .zip files found in {cfg.input_dir}/")
        print()
        out.info("To get started:")
        out.info("  1. Download your data export from Instagram or ChatGPT")
        out.info(f"  2. Drop the .zip file into {cfg.input_dir}/")
        out.info("  3. Run this command again")
        return None

    out.header("Archives found")
    print()
    for i, path in enumerate(archives, 1):
        size_mb = path.stat().st_size / (1024 * 1024)
        guessed = _guess_provider(path.name)
        tag = f"  {out.dim(f'({guessed})')}" if guessed else ""
        print(f"  {out.bold(str(i))}. {path.name}  {out.dim(f'{size_mb:.1f} MB')}{tag}")
    print()

    choice = input(f"  Which archive? [1-{len(archives)}]: ").strip()
    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(archives)):
            raise ValueError
    except ValueError:
        out.error("Invalid choice.")
        return None

    selected = archives[idx]
    guessed = _guess_provider(selected.name)

    if guessed:
        confirm = input(f"  Provider? [{guessed}]: ").strip().lower()
        provider_str = confirm if confirm else guessed
    else:
        prompt = f"  Provider ({', '.join(provider_list)}): "
        provider_str = input(prompt).strip().lower()

    if provider_str not in provider_list:
        choices = ", ".join(provider_list)
        out.error(f"Unknown provider '{provider_str}'. Choose from: {choices}")
        return None

    return provider_str, str(selected)


def resolve_archive(
    args: argparse.Namespace,
    cfg: Config,
    *,
    command: str = "ingest",
) -> tuple[str, str] | None:
    """Resolve ``(provider_str, zip_path)`` from CLI args or interactive picker.

    Returns ``None`` if the user aborts the interactive picker.
    Calls ``sys.exit(1)`` on invalid args.
    """
    provider_list = providers()

    if args.provider is None:
        return pick_archive_interactive(cfg)

    if args.path is None:
        out.error("Please provide both provider and path, or omit both.")
        out.info(f"  Direct:       context-use {command} instagram export.zip")
        out.info(f"  Interactive:  context-use {command}")
        sys.exit(1)

    provider_str = args.provider.lower()
    zip_path = args.path

    if provider_str not in provider_list:
        out.error(
            f"Unknown provider '{provider_str}'. "
            f"Choose from: {', '.join(provider_list)}"
        )
        sys.exit(1)

    if not Path(zip_path).exists():
        out.error(f"File not found: {zip_path}")
        sys.exit(1)

    return provider_str, zip_path


def add_archive_args(parser: argparse.ArgumentParser) -> None:
    """Add the standard positional ``provider`` and ``path`` args.

    Used by every command that accepts a provider archive (ingest, pipeline).
    Both args are optional to allow interactive mode when omitted.
    """
    parser.add_argument(
        "provider",
        nargs="?",
        choices=providers(),
        default=None,
        help="Data provider (omit for interactive mode)",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to .zip archive (omit for interactive mode)",
    )


def print_ingest_result(result: PipelineResult) -> None:
    """Display the counts and per-interaction breakdown from an ingest result."""
    out.kv("Threads created", f"{result.threads_created:,}")
    out.kv("Tasks completed", result.tasks_completed)

    if result.breakdown:
        for b in result.breakdown:
            label = b.interaction_type.replace("_", " ").title()
            out.kv(label, f"{b.thread_count:,} threads", indent=4)


# ── Base command classes ──────────────────────────────────────────────────────


class BaseCommand(ABC):
    """Base class for all CLI commands.

    Subclasses set ``name``, ``help``, and optionally ``description``.
    ``register()`` wires the command into an argparse subparsers action.
    ``execute()`` is the coroutine that runs when the command is invoked.
    """

    name: ClassVar[str]
    help: ClassVar[str] = ""
    description: ClassVar[str] = ""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:  # noqa: B027
        """Override to add arguments to the command's parser."""

    @abstractmethod
    async def execute(self, args: argparse.Namespace) -> None:
        """Entry point called by main()."""

    def register(self, sub: argparse._SubParsersAction) -> argparse.ArgumentParser:  # type: ignore[type-arg]
        """Add this command to *sub* and bind ``args.func`` to ``self.execute``."""
        p = sub.add_parser(
            self.name,
            help=self.help,
            description=self.description or None,
        )
        self.add_arguments(p)
        p.set_defaults(func=self.execute)
        return p


class ContextCommand(BaseCommand, ABC):
    """Command that needs a :class:`ContextUse` instance.

    Execution flow::

        load_config()
            → _prepare(cfg, args)   ← override to add checks / mutate cfg
            → build_ctx(cfg)
            → await ctx.init()
            → await run(cfg, ctx, args)

    Subclasses implement ``run(cfg, ctx, args)``.
    Set ``llm_mode = "sync"`` to use the real-time LLM client instead of
    the batch client.
    """

    llm_mode: ClassVar[str] = "batch"

    async def execute(self, args: argparse.Namespace) -> None:
        cfg = load_config()
        cfg = self._prepare(cfg, args)
        try:
            ctx = build_ctx(cfg, llm_mode=self.llm_mode)
        except ImportError as exc:
            out.error(str(exc))
            sys.exit(1)
        await ctx.init()
        await self.run(cfg, ctx, args)

    def _prepare(self, cfg: Config, args: argparse.Namespace) -> Config:
        """Pre-flight hook. Return (possibly mutated) cfg."""
        cfg.ensure_dirs()
        return cfg

    @abstractmethod
    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        """Override with the command's actual logic."""


class ApiCommand(ContextCommand, ABC):
    """Command that requires a configured OpenAI API key.

    ``_prepare`` enforces ``require_api_key`` before a context is built.
    """

    def _prepare(self, cfg: Config, args: argparse.Namespace) -> Config:
        require_api_key(cfg)
        return super()._prepare(cfg, args)


# ── Command group ─────────────────────────────────────────────────────────────


class CommandGroup:
    """A named container of :class:`BaseCommand` subclasses.

    Declare a group by subclassing and setting ``name``, ``help``, and
    ``subcommands``::

        class MemoriesGroup(CommandGroup):
            name = "memories"
            help = "Manage memories"
            subcommands = [
                MemoriesGenerateCommand,
                MemoriesListCommand,
                MemoriesSearchCommand,
                MemoriesExportCommand,
            ]

    ``register()`` adds the group parser and recursively registers each
    subcommand. When invoked without a subcommand, the group parser prints its
    own help.
    """

    name: ClassVar[str]
    help: ClassVar[str] = ""
    description: ClassVar[str] = ""
    subcommands: ClassVar[list[type[BaseCommand]]]

    def register(self, sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
        p = sub.add_parser(
            self.name,
            help=self.help,
            description=self.description or None,
        )

        async def _show_help(_args: argparse.Namespace) -> None:
            p.print_help()

        p.set_defaults(func=_show_help)
        group_sub = p.add_subparsers(title=f"{self.name} commands")
        for cmd_class in self.subcommands:
            cmd_class().register(group_sub)

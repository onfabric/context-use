from __future__ import annotations

import argparse
import asyncio
import sys
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from context_use.cli import output as out
from context_use.cli.config import build_ctx, load_config, save_config

if TYPE_CHECKING:
    from context_use import ContextUse
    from context_use.batch.manager import ScheduleInstruction
    from context_use.batch.states import State
    from context_use.cli.config import Config
    from context_use.models.batch import Batch
    from context_use.types import PipelineResult


def _batch_detail_from_state(state: State | None) -> str:
    if state is None:
        return ""
    from context_use.asset_description.states import DescGenerateCompleteState
    from context_use.batch.states import FailedState
    from context_use.memories.states import (
        MemoryEmbedCompleteState,
        MemoryGenerateCompleteState,
    )

    if isinstance(state, FailedState):
        message = state.error_message.strip()
        if not message:
            return ""
        return message.splitlines()[0]

    if isinstance(state, MemoryGenerateCompleteState):
        if state.memories_count > 0:
            return f"{state.memories_count} memories generated"
        if state.created_memory_ids:
            return f"{len(state.created_memory_ids)} memories stored"
        return ""

    if isinstance(state, MemoryEmbedCompleteState):
        return f"{state.embedded_count} memories embedded"

    if isinstance(state, DescGenerateCompleteState):
        return f"{state.descriptions_count} descriptions generated"

    return ""


def _safe_current_state(batch: Batch) -> State:
    from context_use.batch.states import CreatedState

    try:
        return batch.parse_current_state()
    except Exception:
        return CreatedState()


class MemoryBatchStatusSpinner(out.BatchStatusSpinner):
    _STYLES: dict[type[State], str] | None = None

    @classmethod
    def _ensure_memory_styles(cls) -> None:
        if cls._STYLES is not None:
            return
        from context_use.memories.states import (
            MemoryEmbedCompleteState,
            MemoryEmbedPendingState,
            MemoryGenerateCompleteState,
            MemoryGeneratePendingState,
        )

        cls._STYLES = {
            **out._base_styles(),
            MemoryGeneratePendingState: "bright_cyan",
            MemoryGenerateCompleteState: "chartreuse1",
            MemoryEmbedPendingState: "bright_blue",
            MemoryEmbedCompleteState: "chartreuse1",
        }


def _build_batch_rows(
    batches: list[Batch],
) -> list[tuple[str, str, State, str]]:
    rows: list[tuple[str, str, State, str]] = []
    for b in batches:
        state = _safe_current_state(b)
        rows.append(
            (
                b.id,
                f"Batch {b.batch_number:03d}",
                state,
                _batch_detail_from_state(state),
            )
        )
    return rows


def create_memory_reporter(batches: list[Batch]) -> out.BatchReporter:
    rows = _build_batch_rows(batches)
    if sys.stdout.isatty():
        MemoryBatchStatusSpinner._ensure_memory_styles()
        return MemoryBatchStatusSpinner(rows)
    return out.LogBatchReporter(rows)


async def _advance_and_update(
    ctx: ContextUse,
    batch_id: str,
    reporter: out.BatchReporter,
) -> ScheduleInstruction:
    instruction = await ctx.advance_batch(batch_id)
    batch = await ctx.get_batch(batch_id)
    if batch is not None:
        try:
            state = batch.parse_current_state()
            reporter.update(batch_id, state, detail=_batch_detail_from_state(state))
        except Exception:
            out.warn(f"Error parsing state for batch {batch_id}")
    return instruction


def create_batch_reporter(batches: list[Batch]) -> out.BatchReporter:
    """Generic reporter using base styles only — works for any batch category."""
    rows = _build_batch_rows(batches)
    if sys.stdout.isatty():
        return out.BatchStatusSpinner(rows)
    return out.LogBatchReporter(rows)


async def run_batches(
    ctx: ContextUse,
    batches: list[Batch],
    *,
    should_sleep_after_each_batch: bool = True,
    reporter_factory: (Callable[[list[Batch]], out.BatchReporter] | None) = None,
) -> None:
    if not batches:
        return

    factory = reporter_factory or create_memory_reporter
    next_due: dict[str, float] = {b.id: 0.0 for b in batches}

    with factory(batches) as reporter:
        pending = reporter.pending_ids
        while pending:
            advanced_any = False

            for batch in batches:
                batch_id = batch.id
                if batch_id not in pending:
                    continue
                if next_due[batch_id] > time.monotonic():
                    continue

                instruction = await _advance_and_update(ctx, batch_id, reporter)
                advanced_any = True

                if instruction.stop:
                    pending.discard(batch_id)
                    continue

                countdown = float(instruction.countdown or 0)
                if not should_sleep_after_each_batch:
                    countdown = 0
                next_due[batch_id] = time.monotonic() + countdown

            if not pending:
                break

            await asyncio.sleep(0 if advanced_any else 0.1)


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
        "Run 'context-use config set-key <key>' or set OPENAI_API_KEY."
    )
    sys.exit(1)


def prompt_api_key(cfg: Config) -> Config:
    """Interactively prompt for an API key, save it, and return updated cfg.

    Calls ``sys.exit(1)`` if the user does not enter a key.
    """
    out.warn("OpenAI API key not configured.")
    out.info("Get an API key at https://platform.openai.com/api-keys")
    print()

    key = input("  Enter your OpenAI API key: ").strip()
    if not key:
        out.error("No key entered — cannot continue.")
        sys.exit(1)

    cfg.openai_api_key = key
    path = save_config(cfg)
    out.success(f"API key saved to {path}")
    print()
    return cfg


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
    """Interactive picker: list archives in context-use-data/input and let user choose.

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


def pick_provider_interactive(
    provider_list: list[str], *, default: str | None = None
) -> str | None:
    """Interactive picker: list providers and let user choose one."""
    if not provider_list:
        out.error("No providers are registered.")
        return None

    out.header("Supported providers")
    print()
    for i, provider in enumerate(provider_list, 1):
        print(f"  {out.bold(str(i))}. {provider}")
    print()

    if default and default in provider_list:
        default_idx = provider_list.index(default) + 1
        choice = input(f"  Choose provider [1-{len(provider_list)}] [{default_idx}]: ")
        choice = choice.strip()
        if not choice:
            return default
    else:
        choice = input(f"  Choose provider [1-{len(provider_list)}]: ").strip()

    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(provider_list)):
            raise ValueError
    except ValueError:
        out.error("Invalid choice.")
        return None

    return provider_list[idx]


def prepare_quick_archive_args(
    args: argparse.Namespace, *, command: str = "pipeline"
) -> None:
    """Validate and complete quick-mode archive args in-place."""
    provider_list = providers()

    zip_path = args.zip_path
    if (
        zip_path is None
        and args.provider is not None
        and args.provider not in provider_list
    ):
        zip_path = args.provider
        args.provider = None

    if zip_path is None:
        out.error("Quick mode requires a zip-path.")
        out.info(f"  Quick:        context-use {command} --quick <zip-path>")
        sys.exit(1)

    if not Path(zip_path).exists():
        out.error(f"File not found: {zip_path}")
        sys.exit(1)
    args.zip_path = zip_path

    if args.provider is not None:
        return

    guessed = _guess_provider(Path(zip_path).name)
    provider = pick_provider_interactive(provider_list, default=guessed)
    if provider is None:
        out.error("Provider selection required in quick mode.")
        sys.exit(1)

    args.provider = provider


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
    zip_path = args.zip_path

    if args.provider is None:
        return pick_archive_interactive(cfg)

    if zip_path is None:
        out.error("Please provide both provider and zip-path, or omit both.")
        out.info(f"  Direct:       context-use {command} <provider> <zip-path>")
        out.info(f"  Interactive:  context-use {command}")
        sys.exit(1)

    provider_str = args.provider.lower()

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
    """Add the standard positional ``provider`` and ``zip-path`` args.

    Used by every command that accepts a provider archive (ingest, pipeline).
    Both args are optional to allow interactive mode when omitted.
    """
    parser.add_argument(
        "provider",
        nargs="?",
        default=None,
        help="Data provider (omit for interactive mode)",
    )
    parser.add_argument(
        "zip_path",
        nargs="?",
        default=None,
        metavar="zip-path",
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

    If no key is configured, ``_prepare`` interactively prompts the user
    to enter one and saves it before proceeding.
    """

    def _prepare(self, cfg: Config, args: argparse.Namespace) -> Config:
        if not cfg.openai_api_key:
            cfg = prompt_api_key(cfg)
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

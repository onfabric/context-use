import argparse
import asyncio
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from context_use.cli import output as out
from context_use.config import Config, build_ctx, load_config, save_config

if TYPE_CHECKING:
    from context_use import ContextUse
    from context_use.batch.states import State
    from context_use.facade.types import PipelineResult
    from context_use.models.batch import Batch


def _batch_detail_from_state(state: "State | None") -> str:
    if state is None:
        return ""
    from context_use.batch.states import FailedState

    if isinstance(state, FailedState):
        message = state.error_message.strip()
        if not message:
            return ""
        return message.splitlines()[0]
    memories_count = getattr(state, "memories_count", None)
    if isinstance(memories_count, int):
        return f"{memories_count} memories generated"
    embedded_count = getattr(state, "embedded_count", None)
    if isinstance(embedded_count, int):
        return f"{embedded_count} memories embedded"
    created_ids = getattr(state, "created_memory_ids", None)
    if isinstance(created_ids, list):
        return f"{len(created_ids)} memories stored"
    return ""


def _is_terminal_state(state: "State | None") -> bool:
    from context_use.batch.states import StopState

    return state is not None and isinstance(state, StopState)


def _safe_current_state(batch: "Batch") -> "State":
    from context_use.batch.states import CreatedState

    try:
        parsed = batch.parse_current_state()
        return parsed
    except Exception:
        return CreatedState()


async def run_batches(
    ctx: ContextUse,
    batches: list[Batch],
    *,
    should_sleep_after_each_batch: bool = True,
) -> None:
    """Drive all batches to completion, polling until each stops."""
    from context_use.batch.manager import ScheduleInstruction

    if not batches:
        return

    ordered_batch_ids = [batch.id for batch in batches]
    next_due_at: dict[str, float] = {batch_id: 0.0 for batch_id in ordered_batch_ids}
    initial_state = {batch.id: _safe_current_state(batch) for batch in batches}
    latest_state: dict[str, State] = dict(initial_state)
    latest_detail: dict[str, str] = {}
    for batch in batches:
        state = initial_state[batch.id]
        latest_detail[batch.id] = _batch_detail_from_state(state)

    batch_rows = [
        (
            batch.id,
            f"Batch {batch.batch_number:03d}",
            latest_state[batch.id],
            latest_detail[batch.id],
        )
        for batch in batches
    ]
    pending_batch_ids: set[str] = {
        batch.id for batch in batches if not _is_terminal_state(initial_state[batch.id])
    }

    with out.BatchStatusSpinner(batch_rows) as spinner:
        while pending_batch_ids:
            advanced_any = False

            for batch_id in ordered_batch_ids:
                if batch_id not in pending_batch_ids:
                    continue

                if next_due_at[batch_id] > time.monotonic():
                    continue

                instruction: ScheduleInstruction = await ctx.advance_batch(batch_id)
                head_state = await ctx.get_batch_head_state(batch_id)
                state = head_state if head_state is not None else latest_state[batch_id]
                detail = _batch_detail_from_state(state)
                latest_state[batch_id] = state
                if detail:
                    latest_detail[batch_id] = detail
                advanced_any = True

                if instruction.stop:
                    spinner.update(
                        batch_id,
                        state,
                        detail=latest_detail[batch_id],
                    )
                    pending_batch_ids.remove(batch_id)
                    continue

                countdown = float(instruction.countdown or 0)
                if not should_sleep_after_each_batch:
                    countdown = 0
                next_due_at[batch_id] = time.monotonic() + countdown
                spinner.update(batch_id, state, detail=latest_detail[batch_id])

            if not pending_batch_ids:
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

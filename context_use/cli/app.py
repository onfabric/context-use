from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Coroutine
from datetime import UTC, date, datetime, timedelta
from itertools import groupby
from pathlib import Path
from typing import Any

from context_use import ContextUse
from context_use.cli import output as out
from context_use.cli.config import (
    Config,
    config_exists,
    config_path_display,
    load_config,
    save_config,
)

DESCRIPTION = """\
context-use — turn your data exports into AI memory

Turn data exports from ChatGPT, Instagram, and other services into
searchable personal memories. context-use extracts your interactions,
generates first-person memories via LLM, and serves them through an
MCP server so AI assistants can know about you.

Quick start: context-use quickstart

No database or config file needed. Results are exported to ./data/output/."""


# ── Infrastructure helpers ──────────────────────────────────────────


def _config_to_dict(cfg: Config, *, llm_mode: str = "batch") -> dict:
    """Convert CLI Config into the canonical config dict for ContextUse."""
    store_config: dict[str, Any] = {}
    if cfg.store_provider == "postgres":
        store_config = {
            "host": cfg.db_host,
            "port": cfg.db_port,
            "database": cfg.db_name,
            "user": cfg.db_user,
            "password": cfg.db_password,
        }

    return {
        "storage": {"provider": "disk", "config": {"base_path": cfg.storage_path}},
        "store": {"provider": cfg.store_provider, "config": store_config},
        "llm": {"api_key": cfg.openai_api_key or "", "mode": llm_mode},
    }


def _build_ctx(cfg: Config):
    from context_use import ContextUse

    return ContextUse.from_config(_config_to_dict(cfg))


def _providers() -> list[str]:
    from context_use import Provider

    return [p.value for p in Provider]


def _ensure_api_key(cfg: Config) -> None:
    """Ensure an API key is available, prompting interactively if needed.

    Used by ``cmd_quickstart`` only — the zero-config entry point.
    """
    if cfg.openai_api_key:
        return
    if sys.stdin.isatty():
        print()
        out.info("Memory generation requires an OpenAI API key.")
        out.info("Get one at https://platform.openai.com/api-keys")
        print()
        key = input("  OpenAI API key: ").strip()
        if key:
            cfg.openai_api_key = key
            save_config(cfg)
            out.success("API key saved")
            print()
            return
    out.error(
        "OpenAI API key not configured. "
        "Run 'context-use config set-key' or set OPENAI_API_KEY."
    )
    sys.exit(1)


def _require_api_key(cfg: Config) -> None:
    """Exit with guidance if no API key is configured.

    Used by Postgres commands — no inline prompting.
    """
    if cfg.openai_api_key:
        return
    out.error(
        "OpenAI API key not configured. "
        "Run 'context-use config set-key' or set OPENAI_API_KEY."
    )
    sys.exit(1)


def _require_persistent(cfg: Config, command: str) -> None:
    """Exit with guidance if the store is not PostgreSQL."""
    if cfg.store_provider == "postgres":
        return
    out.error(f"'{command}' requires PostgreSQL for persistent storage.")
    print()
    out.info("To try context-use without a database:")
    out.next_step("context-use quickstart")
    print()
    out.info("To set up PostgreSQL:")
    out.next_step("context-use config set-store postgres")
    sys.exit(1)


# ── config ──────────────────────────────────────────────────────────


async def cmd_config_show(args: argparse.Namespace) -> None:
    """Display current configuration."""
    cfg = load_config()

    out.header(f"Configuration ({config_path_display()})")
    print()

    if cfg.openai_api_key:
        masked = cfg.openai_api_key[:7] + "..." + cfg.openai_api_key[-4:]
        out.kv("OpenAI API key", masked)
    else:
        out.kv("OpenAI API key", out.dim("not set"))

    if cfg.store_provider == "postgres":
        out.kv("Store", f"postgres ({cfg.db_host}:{cfg.db_port}/{cfg.db_name})")
    else:
        out.kv("Store", "memory (in-memory, no persistence)")

    out.kv("Data directory", cfg.data_dir)

    print()
    out.info("To change settings:")
    out.next_step("context-use config set-key", "change OpenAI API key")
    out.next_step("context-use config set-store postgres", "set up PostgreSQL")
    out.next_step("context-use config set-store memory", "switch to in-memory")
    print()


async def cmd_config_set_key(args: argparse.Namespace) -> None:
    """Prompt for and save a new OpenAI API key."""
    cfg = load_config() if config_exists() else Config()

    out.info("Get an API key at https://platform.openai.com/api-keys")
    print()

    if cfg.openai_api_key:
        masked = cfg.openai_api_key[:7] + "..." + cfg.openai_api_key[-4:]
        out.kv("Current key", masked)

    key = input("  New OpenAI API key: ").strip()
    if not key:
        out.warn("No key entered — keeping current value.")
        return

    cfg.openai_api_key = key
    path = save_config(cfg)
    out.success(f"API key saved to {path}")


async def cmd_config_set_store(args: argparse.Namespace) -> None:
    """Configure the store backend (postgres or memory)."""
    cfg = load_config() if config_exists() else Config()
    backend = args.backend

    if backend == "memory":
        cfg.store_provider = "memory"
        path = save_config(cfg)
        out.success(f"Store set to in-memory. Config written to {path}")
        out.info("Data will only persist for the duration of a single command.")
        out.info("Use 'context-use quickstart' to ingest + generate in one session.")
        return

    # postgres
    cfg.store_provider = "postgres"

    out.info("Setting up PostgreSQL for persistent storage across sessions.")
    out.info("For trying it out without PostgreSQL, run 'context-use quickstart'\n")

    if shutil.which("docker") is not None:
        prompt_text = "  Start a local Postgres container with Docker? [Y/n] "
        start_db = input(prompt_text).strip().lower()
        if start_db in ("", "y", "yes"):
            _start_docker_postgres(cfg)

    host = input(f"  Database host [{cfg.db_host}]: ").strip() or cfg.db_host
    port = input(f"  Database port [{cfg.db_port}]: ").strip() or str(cfg.db_port)
    name = input(f"  Database name [{cfg.db_name}]: ").strip() or cfg.db_name
    user = input(f"  Database user [{cfg.db_user}]: ").strip() or cfg.db_user
    password = (
        input(f"  Database password [{cfg.db_password}]: ").strip() or cfg.db_password
    )
    cfg.db_host = host
    cfg.db_port = int(port)
    cfg.db_name = name
    cfg.db_user = user
    cfg.db_password = password

    path = save_config(cfg)
    out.success(f"PostgreSQL configured. Config written to {path}")

    try:
        ctx = _build_ctx(cfg)
        await ctx.init()
        out.success("Database initialised")
    except Exception as exc:
        out.warn(f"Could not initialise database: {exc}")
        out.info("You can retry later with: context-use config set-store postgres")

    print()
    out.header("You're all set! Next steps:")
    print()
    out.info("Run the full pipeline:")
    out.next_step("context-use pipeline")
    out.info("Or step by step:")
    out.next_step("context-use ingest")
    out.next_step("context-use memories generate")
    out.next_step("context-use profile generate")
    out.info("Start the MCP server:")
    out.next_step("python -m context_use.ext.mcp_use.run")
    print()


async def cmd_config_path(args: argparse.Namespace) -> None:
    """Print the config file path."""
    print(config_path_display())


def _start_docker_postgres(cfg: Config) -> None:
    """Start a Postgres container via docker run."""
    # Verify the Docker daemon is reachable before attempting anything.
    probe = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        out.error("Docker daemon is not running.")
        out.info("Start Docker Desktop (or the docker service) and try again:")
        out.next_step("context-use config set-store postgres")
        sys.exit(1)

    container_name = "context-use-postgres"

    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and "true" in result.stdout:
        out.success("Postgres container already running")
        return

    subprocess.run(
        ["docker", "rm", "-f", container_name],
        capture_output=True,
    )

    out.info("Starting Postgres container...")
    result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "-p",
            f"{cfg.db_port}:5432",
            "-e",
            f"POSTGRES_USER={cfg.db_user}",
            "-e",
            f"POSTGRES_PASSWORD={cfg.db_password}",
            "-e",
            f"POSTGRES_DB={cfg.db_name}",
            "-v",
            "context-use-pgdata:/var/lib/postgresql/data",
            "pgvector/pgvector:pg17",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        out.success(f"Postgres running on localhost:{cfg.db_port}")
        import time

        out.info("Waiting for Postgres to be ready...")
        time.sleep(3)
    else:
        out.error(f"Failed to start Postgres: {result.stderr.strip()}")
        sys.exit(1)


# ── ingest ──────────────────────────────────────────────────────────


def _scan_input_dir(input_dir: Path) -> list[Path]:
    """Find all .zip files in the input directory."""
    if not input_dir.exists():
        return []
    return sorted(input_dir.glob("*.zip"), key=lambda p: p.name)


def _guess_provider(filename: str) -> str | None:
    """Try to guess the provider from the archive filename."""
    name = filename.lower()
    for provider in _providers():
        if provider in name:
            return provider
    return None


def _pick_archive_interactive(cfg: Config) -> tuple[str, str] | None:
    """Interactive picker: list archives in data/input, let user choose."""
    cfg.ensure_dirs()
    archives = _scan_input_dir(cfg.input_dir)
    providers = _providers()

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
        provider_str = input(f"  Provider ({', '.join(providers)}): ").strip().lower()

    if provider_str not in providers:
        choices = ", ".join(providers)
        out.error(f"Unknown provider '{provider_str}'. Choose from: {choices}")
        return None

    return provider_str, str(selected)


async def cmd_ingest(args: argparse.Namespace) -> None:
    from context_use import Provider

    cfg = load_config()
    _require_persistent(cfg, "ingest")
    providers = _providers()

    if args.provider is None:
        picked = _pick_archive_interactive(cfg)
        if picked is None:
            return
        provider_str, zip_path = picked
    elif args.path is None:
        out.error("Please provide both provider and path, or omit both.")
        out.info("  Direct:      context-use ingest instagram export.zip")
        out.info("  Interactive:  context-use ingest")
        sys.exit(1)
    else:
        provider_str = args.provider.lower()
        zip_path = args.path

        if provider_str not in providers:
            choices = ", ".join(providers)
            out.error(f"Unknown provider '{provider_str}'. Choose from: {choices}")
            sys.exit(1)

        if not Path(zip_path).exists():
            out.error(f"File not found: {zip_path}")
            sys.exit(1)

    provider = Provider(provider_str)

    print()
    out.header(f"Ingesting {provider.value} archive")
    out.kv("File", zip_path)
    out.kv("Provider", provider.value)
    print()

    ctx = _build_ctx(cfg)
    await ctx.init()

    result = await ctx.process_archive(provider, zip_path)

    out.success("Archive processed")
    out.kv("Archive ID", result.archive_id)
    out.kv("Threads created", f"{result.threads_created:,}")
    out.kv("Tasks completed", result.tasks_completed)
    if result.tasks_failed:
        out.kv("Tasks failed", result.tasks_failed)
    if result.errors:
        for e in result.errors:
            out.error(e)

    if result.breakdown:
        print()
        out.info("Breakdown:")
        for b in result.breakdown:
            label = b.interaction_type.replace("_", " ").title()
            out.kv(label, f"{b.thread_count:,} threads", indent=4)

    print()
    out.header("Next step:")
    out.next_step("context-use memories generate")
    print()


# ── quickstart (ingest → memories → profile, always real-time API) ──


async def cmd_quickstart(args: argparse.Namespace) -> None:
    """Ingest an archive and run the full pipeline in one session.

    Always uses the real-time API (no batch polling). Default: last 30
    days. Use ``--full`` to process the entire archive.
    """
    from context_use import Provider

    cfg = load_config()
    # Always use memory store for quickstart
    cfg.store_provider = "memory"
    cfg.ensure_dirs()
    _ensure_api_key(cfg)
    providers = _providers()

    if args.provider is None:
        picked = _pick_archive_interactive(cfg)
        if picked is None:
            return
        provider_str, zip_path = picked
    elif args.path is None:
        out.error("Please provide both provider and path, or omit both.")
        out.info("  Direct:      context-use quickstart instagram export.zip")
        out.info("  Interactive:  context-use quickstart")
        sys.exit(1)
    else:
        provider_str = args.provider.lower()
        zip_path = args.path
        if provider_str not in providers:
            out.error(
                f"Unknown provider '{provider_str}'. "
                f"Choose from: {', '.join(providers)}"
            )
            sys.exit(1)
        if not Path(zip_path).exists():
            out.error(f"File not found: {zip_path}")
            sys.exit(1)

    full = args.full
    since = None if full else datetime.now(UTC) - timedelta(days=args.last_days)

    if full and sys.stdin.isatty():
        print()
        out.warn(
            "Processing the full archive with the real-time API. "
            "Large archives may hit OpenAI rate limits and take "
            "significantly longer."
        )
        out.info("For large archives, consider using PostgreSQL with the batch API:")
        out.next_step("context-use config set-store postgres")
        print()
        confirm = input("  Continue? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            out.info("Aborted.")
            return

    provider = Provider(provider_str)
    ctx_dict = _config_to_dict(cfg, llm_mode="sync")
    ctx = ContextUse.from_config(ctx_dict)
    await ctx.init()

    # Phase 1: Ingest
    print()
    out.header(f"Phase 1/3 · Ingesting {provider.value} archive")
    out.kv("File", zip_path)
    print()

    result = await ctx.process_archive(provider, zip_path)

    out.success("Archive processed")
    out.kv("Threads created", f"{result.threads_created:,}")
    out.kv("Tasks completed", result.tasks_completed)

    if result.breakdown:
        for b in result.breakdown:
            label = b.interaction_type.replace("_", " ").title()
            out.kv(label, f"{b.thread_count:,} threads", indent=4)
    print()

    if result.tasks_failed:
        out.error(f"{result.tasks_failed} tasks failed — stopping")
        return

    # Phase 2: Memories (always real-time API)
    out.header("Phase 2/3 · Generating memories")
    out.info("Using real-time API.")
    if since:
        out.kv("Since", since.strftime("%Y-%m-%d"))
        out.info(f"Only processing the last {args.last_days} days as a preview.")
    else:
        out.info("Processing full archive history.")
    print()

    mem_result = await ctx.generate_memories([result.archive_id], since=since)

    out.success("Memories generated")
    out.kv("Batches", mem_result.batches_created)

    count = await ctx.count_memories()
    out.kv("Active memories", f"{count:,}")
    print()

    if count == 0:
        out.warn("No memories generated — skipping profile")
        if (
            not full
            and mem_result.threads_total > 0
            and mem_result.threads_after_filter == 0
        ):
            print()
            out.info(
                f"All {mem_result.threads_total} threads are older than "
                f"{args.last_days} days."
            )
            out.info("Try including more history:")
            out.next_step(
                f"context-use quickstart --last-days 90 {provider.value} {zip_path}"
            )
            out.info("Or process the full archive:")
            out.next_step(f"context-use quickstart --full {provider.value} {zip_path}")
        return

    # Phase 3: Profile
    profile = None
    if not args.skip_profile:
        out.header("Phase 3/3 · Generating profile")
        print()

        profile_summary = await ctx.generate_profile()
        profile = profile_summary

        out.success("Profile generated")
        out.kv("Memory count", profile.memory_count)
        out.kv("Length", f"{len(profile.content):,} chars")
        print()

    # ── Show results ─────────────────────────────────────────────
    memories = await ctx.list_memories()

    if memories:
        out.header(f"Your memories ({len(memories):,})")
        print()
        for m in memories[:10]:
            date_str = m.from_date.isoformat()
            print(f"  [{date_str}] {m.content}")
        if len(memories) > 10:
            out.info(f"  ... and {len(memories) - 10:,} more")
        print()

    if profile is not None:
        out.header("Your profile")
        out.rule()
        print(profile.content)
        out.rule()
        print()

    # ── Export to files ──────────────────────────────────────────
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    exported: list[str] = []

    if memories:
        md_path = cfg.output_dir / f"memories_{ts}.md"
        _export_memories_markdown(memories, md_path)
        json_path = cfg.output_dir / f"memories_{ts}.json"
        _export_memories_json(memories, json_path)
        exported.append(f"Memories  → {md_path}")
        exported.append(f"           {json_path}")

    if profile is not None:
        prof_path = cfg.output_dir / f"profile_{ts}.md"
        prof_path.write_text(profile.content, encoding="utf-8")
        exported.append(f"Profile   → {prof_path}")

    if exported:
        out.header("Exported")
        for line in exported:
            out.success(line)
        print()

    out.success("Pipeline complete!")

    # ── Next steps ───────────────────────────────────────────────
    print()
    out.header("What's next:")
    print()
    out.info(
        "This was a preview. To search, query, and connect your "
        "memories to AI assistants, set up PostgreSQL:"
    )
    out.next_step("context-use config set-store postgres")
    print()
    out.info("Then run the full pipeline with the batch API:")
    out.next_step("context-use pipeline")
    print()


# ── pipeline (ingest → memories → profile, persistent store) ────────


async def cmd_pipeline(args: argparse.Namespace) -> None:
    """Run the full pipeline (ingest → memories → profile) with PostgreSQL.

    Uses the batch API for memory generation. Interactive archive picker
    when no arguments are provided.
    """
    from context_use import Provider

    cfg = load_config()
    _require_persistent(cfg, "pipeline")
    _require_api_key(cfg)
    providers = _providers()

    if args.provider is None:
        picked = _pick_archive_interactive(cfg)
        if picked is None:
            return
        provider_str, zip_path = picked
    elif args.path is None:
        out.error("Please provide both provider and path, or omit both.")
        out.info("  Direct:      context-use pipeline instagram export.zip")
        out.info("  Interactive:  context-use pipeline")
        sys.exit(1)
    else:
        provider_str = args.provider.lower()
        zip_path = args.path
        if provider_str not in providers:
            out.error(
                f"Unknown provider '{provider_str}'. "
                f"Choose from: {', '.join(providers)}"
            )
            sys.exit(1)
        if not Path(zip_path).exists():
            out.error(f"File not found: {zip_path}")
            sys.exit(1)

    provider = Provider(provider_str)
    ctx = _build_ctx(cfg)
    await ctx.init()

    # Step 1: Ingest
    print()
    out.header(f"Step 1/3 · Ingesting {provider.value} archive")
    out.kv("File", zip_path)
    print()

    result = await ctx.process_archive(provider, zip_path)

    out.success("Archive processed")
    out.kv("Threads created", f"{result.threads_created:,}")
    out.kv("Tasks completed", result.tasks_completed)

    if result.breakdown:
        for b in result.breakdown:
            label = b.interaction_type.replace("_", " ").title()
            out.kv(label, f"{b.thread_count:,} threads", indent=4)
    print()

    if result.tasks_failed:
        out.error(f"{result.tasks_failed} tasks failed — stopping")
        return

    # Step 2: Memories (batch API)
    out.header("Step 2/3 · Generating memories")
    out.info("Using batch API. This typically takes 2-10 minutes.\n")

    mem_result = await ctx.generate_memories([result.archive_id])

    out.success("Memories generated")
    out.kv("Batches created", mem_result.batches_created)

    count = await ctx.count_memories()
    out.kv("Active memories", f"{count:,}")
    print()

    if count == 0:
        out.warn("No memories generated — skipping profile.")
        return

    # Step 3: Profile
    if not args.skip_profile:
        out.header("Step 3/3 · Generating profile")
        print()

        profile = await ctx.generate_profile()

        out.success("Profile generated")
        out.kv("Length", f"{len(profile.content):,} characters")
        out.kv("Memories used", profile.memory_count)
        print()

    out.success("Pipeline complete!")
    print()
    out.header("What's next:")
    out.next_step("context-use memories list", "browse your memories")
    out.next_step('context-use memories search "query"', "semantic search")
    out.next_step("context-use profile show", "view your profile")
    out.next_step('context-use ask "Tell me about myself"', "try the built-in agent")
    out.next_step("python -m context_use.ext.mcp_use.run", "start the MCP server")
    print()


# ── memories generate ───────────────────────────────────────────────


async def _pick_archive(ctx) -> tuple[str, str] | None:
    """Show archive picker and return (archive_id, provider) or None."""
    archives = await ctx.list_archives()

    if not archives:
        out.warn("No completed archives found. Run 'context-use ingest' first.")
        return None

    out.header("Completed archives")
    print()
    for i, a in enumerate(archives, 1):
        ts = a.created_at.strftime("%Y-%m-%d %H:%M")
        print(
            f"  {out.bold(str(i))}. {a.provider}"
            f"  {out.dim(f'{a.thread_count} threads')}"
            f"  {out.dim(ts)}"
            f"  {out.dim(a.id[:8])}"
        )
    print()

    try:
        choice = input(f"  Which archive? [1-{len(archives)}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(archives)):
            raise ValueError
    except ValueError:
        out.error("Invalid choice.")
        return None

    return archives[idx].id, archives[idx].provider


async def cmd_memories_generate(args: argparse.Namespace) -> None:
    cfg = load_config()
    _require_persistent(cfg, "memories generate")
    _require_api_key(cfg)

    ctx = _build_ctx(cfg)
    await ctx.init()

    picked = await _pick_archive(ctx)
    if picked is None:
        return
    selected_id, selected_provider = picked

    out.header("Generating memories")
    out.info("This submits batch jobs to OpenAI and polls for results.")
    out.info("It typically takes 2-10 minutes depending on data volume.\n")
    out.kv("Archive", f"{selected_provider} ({selected_id[:8]})")

    result = await ctx.generate_memories([selected_id])

    out.success("Memories generated")
    out.kv("Tasks processed", result.tasks_processed)
    out.kv("Batches created", result.batches_created)
    if result.errors:
        for e in result.errors:
            out.error(e)

    memories = await ctx.list_memories()

    if memories:
        first = memories[0].from_date.isoformat()
        last = memories[-1].to_date.isoformat()
        print()
        out.kv("Total memories", f"{len(memories):,}")
        out.kv("Time span", f"{first} to {last}")

        print()
        out.info("Sample memories:")
        for m in memories[:3]:
            date_str = m.from_date.isoformat()
            preview = m.content[:120] + "..." if len(m.content) > 120 else m.content
            out.info(f"  [{date_str}] {preview}")

    print()
    out.header("Next steps:")
    out.next_step("context-use memories refine", "refine overlapping memories")
    out.next_step("context-use profile generate", "create your profile")
    out.next_step("context-use memories list", "browse your memories")
    out.next_step("context-use memories export", "export to markdown")
    print()


# ── memories refine ─────────────────────────────────────────────────


async def cmd_memories_refine(args: argparse.Namespace) -> None:
    cfg = load_config()
    _require_persistent(cfg, "memories refine")
    _require_api_key(cfg)

    ctx = _build_ctx(cfg)
    await ctx.init()

    picked = await _pick_archive(ctx)
    if picked is None:
        return
    selected_id, selected_provider = picked

    out.header("Refining memories")
    out.info("This discovers overlapping memories and merges them via LLM.")
    out.info("It typically takes 1-5 minutes.\n")
    out.kv("Archive", f"{selected_provider} ({selected_id[:8]})")

    result = await ctx.refine_memories([selected_id])

    out.success("Refinement complete")
    out.kv("Batches created", result.batches_created)
    if result.errors:
        for e in result.errors:
            out.error(e)

    print()
    out.header("Next steps:")
    out.next_step("context-use profile generate", "create your profile")
    out.next_step("context-use memories list", "browse your memories")
    print()


# ── memories list ───────────────────────────────────────────────────


async def cmd_memories_list(args: argparse.Namespace) -> None:
    cfg = load_config()
    _require_persistent(cfg, "memories list")

    ctx = _build_ctx(cfg)
    await ctx.init()

    total = await ctx.count_memories()
    memories = await ctx.list_memories(limit=args.limit)

    if not memories:
        out.warn("No memories found. Run 'context-use memories generate' first.")
        return

    if args.limit:
        showing = f"Showing {len(memories)} of {total:,}"
    else:
        showing = f"{total:,} memories"
    out.header(f"Memories ({showing})")
    print()

    by_month = lambda m: m.from_date.strftime("%Y-%m")  # noqa: E731
    for month_key, group in groupby(memories, key=by_month):
        month_label = datetime.strptime(month_key, "%Y-%m").strftime("%B %Y")
        print(f"  {out.bold(month_label)}")
        for m in group:
            date_str = m.from_date.isoformat()
            print(f"    [{date_str}] {m.content}")
        print()


# ── memories search ─────────────────────────────────────────────────


async def cmd_memories_search(args: argparse.Namespace) -> None:
    cfg = load_config()
    _require_persistent(cfg, "memories search")
    _require_api_key(cfg)

    ctx = _build_ctx(cfg)
    await ctx.init()

    from_dt = date.fromisoformat(args.from_date) if args.from_date else None
    to_dt = date.fromisoformat(args.to_date) if args.to_date else None

    results = await ctx.search_memories(
        query=args.query,
        from_date=from_dt,
        to_date=to_dt,
        top_k=args.top_k,
    )

    if not results:
        out.warn("No matching memories found.")
        return

    out.header(f"Search results ({len(results)})")
    print()
    for i, r in enumerate(results, 1):
        if r.similarity is not None:
            sim = f"  {out.dim(f'similarity={r.similarity:.4f}')}"
        else:
            sim = ""
        print(f"  {i}. [{r.from_date}]{sim}")
        print(f"     {r.content}")
    print()


# ── memories export ─────────────────────────────────────────────────


async def cmd_memories_export(args: argparse.Namespace) -> None:
    cfg = load_config()
    _require_persistent(cfg, "memories export")

    ctx = _build_ctx(cfg)
    await ctx.init()

    memories = await ctx.list_memories()

    if not memories:
        out.warn("No memories to export.")
        return

    fmt = args.format
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    default_ext = "md" if fmt == "markdown" else "json"

    if args.out:
        out_path = Path(args.out)
    else:
        cfg.ensure_dirs()
        out_path = cfg.output_dir / f"memories_{ts}.{default_ext}"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "markdown":
        _export_memories_markdown(memories, out_path)
    else:
        _export_memories_json(memories, out_path)

    out.success(f"Exported {len(memories):,} memories to {out_path}")


def _export_memories_markdown(memories: list, path: Path) -> None:
    lines = [
        "# My Memories",
        "",
        f"> Exported by context-use on {datetime.now(UTC).strftime('%Y-%m-%d')}",
        f"> {len(memories):,} memories",
        "",
    ]

    by_month = lambda m: m.from_date.strftime("%Y-%m")  # noqa: E731
    for month_key, group in groupby(memories, key=by_month):
        month_label = datetime.strptime(month_key, "%Y-%m").strftime("%B %Y")
        lines.append(f"## {month_label}")
        lines.append("")
        for m in group:
            if m.from_date == m.to_date:
                date_str = m.from_date.isoformat()
            else:
                date_str = f"{m.from_date.isoformat()} – {m.to_date.isoformat()}"
            lines.append(f"- **{date_str}**: {m.content}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _export_memories_json(memories: list, path: Path) -> None:
    rows = [
        {
            "content": m.content,
            "from_date": m.from_date.isoformat(),
            "to_date": m.to_date.isoformat(),
        }
        for m in memories
    ]
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


# ── profile generate ────────────────────────────────────────────────


async def cmd_profile_generate(args: argparse.Namespace) -> None:
    cfg = load_config()
    _require_persistent(cfg, "profile generate")
    _require_api_key(cfg)

    ctx = _build_ctx(cfg)
    await ctx.init()

    out.header("Generating profile")

    count = await ctx.count_memories()

    if count == 0:
        out.warn("No memories found. Run 'context-use memories generate' first.")
        return

    out.kv("Active memories", f"{count:,}")
    out.kv("Lookback", f"{args.lookback} months")
    print()

    profile = await ctx.generate_profile(lookback_months=args.lookback)

    out.success("Profile generated")
    out.kv("Length", f"{len(profile.content):,} characters")
    out.kv("Memories used", profile.memory_count)
    print()

    out.info("Preview:")
    out.rule()
    preview_lines = profile.content.split("\n")[:12]
    for line in preview_lines:
        print(f"  {line}")
    if len(profile.content.split("\n")) > 12:
        out.info("  ...")
    out.rule()

    print()
    out.header("Next steps:")
    out.next_step("context-use profile show", "view the full profile")
    out.next_step("context-use profile export", "save to a markdown file")
    out.next_step("python -m context_use.ext.mcp_use.run", "start the MCP server")
    out.next_step('context-use ask "Tell me about myself"', "try the built-in agent")
    print()


# ── profile show ────────────────────────────────────────────────────


async def cmd_profile_show(args: argparse.Namespace) -> None:
    cfg = load_config()
    _require_persistent(cfg, "profile show")

    ctx = _build_ctx(cfg)
    await ctx.init()

    profile = await ctx.get_profile()

    if profile is None:
        out.warn("No profile found. Run 'context-use profile generate' first.")
        return

    print()
    print(profile.content)
    print()
    out.info(
        out.dim(
            f"Generated at {profile.generated_at.isoformat()} "
            f"from {profile.memory_count} memories"
        )
    )
    print()


# ── profile export ──────────────────────────────────────────────────


async def cmd_profile_export(args: argparse.Namespace) -> None:
    cfg = load_config()
    _require_persistent(cfg, "profile export")

    ctx = _build_ctx(cfg)
    await ctx.init()

    profile = await ctx.get_profile()

    if profile is None:
        out.warn("No profile found. Run 'context-use profile generate' first.")
        return

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    if args.out:
        out_path = Path(args.out)
    else:
        cfg.ensure_dirs()
        out_path = cfg.output_dir / f"profile_{ts}.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(profile.content, encoding="utf-8")
    out.success(f"Profile exported to {out_path}")


# ── ask ─────────────────────────────────────────────────────────────


async def cmd_ask(args: argparse.Namespace) -> None:
    """Simple RAG agent: search memories + profile, then answer."""
    cfg = load_config()
    _require_persistent(cfg, "ask")
    _require_api_key(cfg)

    ctx = _build_ctx(cfg)
    await ctx.init()

    interactive = args.interactive or args.query is None

    if interactive:
        print()
        out.banner()
        out.info("Ask questions about your memories. Type 'quit' to exit.\n")

    while True:
        if interactive:
            try:
                query = input(out.cyan("> ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not query or query.lower() in ("quit", "exit", "q"):
                break
        else:
            query = args.query

        answer = await ctx.ask(query)
        print(f"\n{answer}\n")

        if not interactive:
            break


# ── Parser ──────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    providers = _providers()

    parser = argparse.ArgumentParser(
        prog="context-use",
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Get started (no setup needed):\n"
            "  context-use quickstart                       "
            "Preview with last 30 days, real-time API\n"
            "\n"
            "Full pipeline (requires PostgreSQL):\n"
            "  1. context-use config set-store postgres     "
            "Set up PostgreSQL (one-time)\n"
            "  2. context-use pipeline                      "
            "Ingest → memories → profile (batch API)\n"
            "\n"
            "Or step by step:\n"
            "  1. context-use ingest                        "
            "Parse an archive\n"
            "  2. context-use memories generate             "
            "Generate memories (batch API)\n"
            "  3. context-use profile generate              "
            "Build your profile\n"
            "\n"
            "Explore:\n"
            "  context-use memories list                    "
            "Browse memories\n"
            '  context-use memories search "query"          '
            "Semantic search\n"
            "  context-use memories export                  "
            "Export to file\n"
            "  context-use profile show                     "
            "View your profile\n"
            '  context-use ask "question"                   '
            "Ask about your memories\n"
            "\n"
            "MCP server:\n"
            "  python -m context_use.ext.mcp_use.run       "
            "Start MCP server for Claude/Cursor\n"
            "\n"
            "Configuration:\n"
            "  context-use config show                      "
            "Show current settings\n"
            "  context-use config set-key                   "
            "Change OpenAI API key\n"
            "  context-use config set-store postgres        "
            "Set up PostgreSQL\n"
            "  context-use config path                      "
            "Print config file location\n"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed progress logs (polling, state transitions)",
    )
    sub = parser.add_subparsers(dest="command", title="commands")

    # quickstart (ingest → memories → profile in one session, real-time API)
    p_qs = sub.add_parser(
        "quickstart",
        help="Try it out — ingest + memories + profile in one session",
        description=(
            "Run the full pipeline (ingest, memories, profile) in one session "
            "using the real-time API. No database needed. "
            "By default processes the last 30 days; use --full for all history."
        ),
    )
    p_qs.add_argument(
        "provider",
        nargs="?",
        choices=providers,
        default=None,
        help="Data provider (omit for interactive mode)",
    )
    p_qs.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to .zip archive (omit for interactive mode)",
    )
    p_qs.add_argument(
        "--skip-profile",
        action="store_true",
        help="Skip profile generation",
    )
    p_qs.add_argument(
        "--full",
        action="store_true",
        help="Process full archive history (default: last 30 days)",
    )
    p_qs.add_argument(
        "--last-days",
        type=int,
        default=30,
        help="Only process threads from the last N days (default: 30)",
    )

    # pipeline (ingest → memories → profile, persistent store, batch API)
    p_pipe = sub.add_parser(
        "pipeline",
        help="Full pipeline — ingest + memories + profile (requires PostgreSQL)",
        description=(
            "Run the full pipeline (ingest, memories, profile) using PostgreSQL "
            "and the batch API. Run without arguments to interactively pick an "
            "archive from data/input/."
        ),
    )
    p_pipe.add_argument(
        "provider",
        nargs="?",
        choices=providers,
        default=None,
        help="Data provider (omit for interactive mode)",
    )
    p_pipe.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to .zip archive (omit for interactive mode)",
    )
    p_pipe.add_argument(
        "--skip-profile",
        action="store_true",
        help="Skip profile generation",
    )

    # ingest
    p_ingest = sub.add_parser(
        "ingest",
        help="Step 1: Process a data export archive (requires PostgreSQL)",
        description=(
            "Process a data export archive. Run without arguments to "
            "interactively pick from archives in data/input/. "
            "Requires PostgreSQL."
        ),
    )
    p_ingest.add_argument(
        "provider",
        nargs="?",
        choices=providers,
        default=None,
        help="Data provider (omit for interactive mode)",
    )
    p_ingest.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to .zip archive (omit for interactive mode)",
    )

    # memories
    p_mem = sub.add_parser("memories", help="Manage memories (requires PostgreSQL)")
    mem_sub = p_mem.add_subparsers(dest="memories_command", title="memories commands")

    mem_sub.add_parser(
        "generate", help="Step 2: Generate memories from ingested archives (batch API)"
    )
    mem_sub.add_parser("refine", help="Refine overlapping memories")

    p_mem_list = mem_sub.add_parser("list", help="List memories")
    p_mem_list.add_argument(
        "--limit", type=int, default=None, help="Max memories to show"
    )

    p_mem_search = mem_sub.add_parser("search", help="Search memories")
    p_mem_search.add_argument("query", nargs="?", help="Semantic search query")
    p_mem_search.add_argument(
        "--from", dest="from_date", help="Start date (YYYY-MM-DD)"
    )
    p_mem_search.add_argument("--to", dest="to_date", help="End date (YYYY-MM-DD)")
    p_mem_search.add_argument("--top-k", type=int, default=10, help="Number of results")

    p_mem_export = mem_sub.add_parser("export", help="Export memories to file")
    p_mem_export.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    p_mem_export.add_argument("--out", metavar="PATH", help="Output file path")

    # profile
    p_prof = sub.add_parser("profile", help="Manage your profile (requires PostgreSQL)")
    prof_sub = p_prof.add_subparsers(dest="profile_command", title="profile commands")

    p_prof_gen = prof_sub.add_parser(
        "generate", help="Step 3: Generate or update your profile"
    )
    p_prof_gen.add_argument(
        "--lookback",
        type=int,
        default=6,
        help="Lookback window in months (default: 6)",
    )

    prof_sub.add_parser("show", help="Display your current profile")

    p_prof_export = prof_sub.add_parser("export", help="Export profile to markdown")
    p_prof_export.add_argument("--out", metavar="PATH", help="Output file path")

    # ask
    p_ask = sub.add_parser(
        "ask", help="Ask a question about your memories (requires PostgreSQL)"
    )
    p_ask.add_argument("query", nargs="?", help="Your question")
    p_ask.add_argument(
        "--interactive", action="store_true", help="Interactive chat mode"
    )

    # config
    p_cfg = sub.add_parser("config", help="View and change settings")
    cfg_sub = p_cfg.add_subparsers(dest="config_command", title="config commands")

    cfg_sub.add_parser("show", help="Show current settings")
    cfg_sub.add_parser("set-key", help="Change OpenAI API key")

    p_cfg_store = cfg_sub.add_parser("set-store", help="Configure the store backend")
    p_cfg_store.add_argument(
        "backend",
        choices=["postgres", "memory"],
        help="Store backend to use",
    )

    cfg_sub.add_parser("path", help="Print config file location")

    return parser


# ── Dispatch ────────────────────────────────────────────────────────

_CommandHandler = Callable[[argparse.Namespace], Coroutine[Any, Any, None]]

_COMMAND_MAP: dict[str, _CommandHandler] = {
    "ingest": cmd_ingest,
    "quickstart": cmd_quickstart,
    "pipeline": cmd_pipeline,
    "ask": cmd_ask,
}

_MEMORIES_MAP: dict[str, _CommandHandler] = {
    "generate": cmd_memories_generate,
    "refine": cmd_memories_refine,
    "list": cmd_memories_list,
    "search": cmd_memories_search,
    "export": cmd_memories_export,
}

_PROFILE_MAP: dict[str, _CommandHandler] = {
    "generate": cmd_profile_generate,
    "show": cmd_profile_show,
    "export": cmd_profile_export,
}

_CONFIG_MAP: dict[str, _CommandHandler] = {
    "show": cmd_config_show,
    "set-key": cmd_config_set_key,
    "set-store": cmd_config_set_store,
    "path": cmd_config_path,
}


def main() -> None:
    import logging

    parser = _build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="  %(name)s: %(message)s",
        )
    logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
    logging.getLogger("litellm").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if not args.command:
        parser.print_help()
        return

    if args.command == "memories":
        if not args.memories_command:
            parser.parse_args(["memories", "--help"])
            return
        handler = _MEMORIES_MAP.get(args.memories_command)
    elif args.command == "profile":
        if not args.profile_command:
            parser.parse_args(["profile", "--help"])
            return
        handler = _PROFILE_MAP.get(args.profile_command)
    elif args.command == "config":
        if not args.config_command:
            parser.parse_args(["config", "--help"])
            return
        handler = _CONFIG_MAP.get(args.config_command)
    else:
        handler = _COMMAND_MAP.get(args.command)

    if handler is None:
        parser.print_help()
        return

    try:
        asyncio.run(handler(args))
    except KeyboardInterrupt:
        print()

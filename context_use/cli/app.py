"""Main CLI application for context-use.

All commands are defined here and wired to the argparse parser.
Each command is an async function that receives the parsed args and
config, run via ``asyncio.run()`` from :func:`main`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Coroutine
from datetime import UTC, date, datetime
from itertools import groupby
from pathlib import Path
from typing import Any

from context_use.cli import output as out
from context_use.cli.config import (
    Config,
    config_exists,
    load_config,
    save_config,
)

DESCRIPTION = "context-use — turn your data exports into AI memory"


# ── Infrastructure helpers ──────────────────────────────────────────


def _config_to_dict(cfg: Config) -> dict:
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
        "llm": {"api_key": cfg.openai_api_key or ""},
    }


def _build_ctx(cfg: Config):
    from context_use import ContextUse

    return ContextUse.from_config(_config_to_dict(cfg))


def _providers() -> list[str]:
    from context_use import Provider

    return [p.value for p in Provider]


def _require_api_key(cfg: Config) -> None:
    if not cfg.openai_api_key:
        out.error(
            "OpenAI API key not configured. "
            "Run 'context-use init' or set OPENAI_API_KEY."
        )
        sys.exit(1)


def _warn_ephemeral(cfg: Config) -> None:
    """Warn if using in-memory store (data doesn't survive across commands)."""
    if cfg.store_provider == "memory":
        out.warn("In-memory store: data from previous commands is not available.")
        out.info(
            "Use 'context-use run' to ingest + generate in one session, "
            "or switch to PostgreSQL via 'context-use init'."
        )
        print()


# ── init ────────────────────────────────────────────────────────────


async def cmd_init(args: argparse.Namespace) -> None:
    out.banner()
    print()
    out.info("This wizard will set up everything you need.\n")

    cfg = load_config() if config_exists() else Config()

    # Step 1: Storage backend
    out.header("Step 1/3 · Storage Backend")
    out.info("context-use can run entirely in-memory (no external dependencies)")
    out.info("or use PostgreSQL for persistent storage across sessions.")
    print()
    use_pg = input("  Use PostgreSQL? [y/N] ").strip().lower()

    if use_pg in ("y", "yes"):
        cfg.store_provider = "postgres"

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
            input(f"  Database password [{cfg.db_password}]: ").strip()
            or cfg.db_password
        )
        cfg.db_host = host
        cfg.db_port = int(port)
        cfg.db_name = name
        cfg.db_user = user
        cfg.db_password = password
        out.success("PostgreSQL configured")
    else:
        cfg.store_provider = "memory"
        out.success("Using in-memory store")
        out.info("  Note: data only lives for a single command invocation.")
        out.info("  Use 'context-use run' to ingest + generate in one session.")

    # Step 2: OpenAI
    out.header("Step 2/3 · OpenAI API Key")
    out.info("Memory generation and search require an OpenAI API key.")
    out.info("Get one at https://platform.openai.com/api-keys")
    print()
    if cfg.openai_api_key:
        masked = cfg.openai_api_key[:7] + "..." + cfg.openai_api_key[-4:]
        change = input(f"  Current key: {masked}. Change it? [y/N] ").strip().lower()
        if change in ("y", "yes"):
            cfg.openai_api_key = input("  OpenAI API key: ").strip()
    else:
        cfg.openai_api_key = input("  OpenAI API key: ").strip()
    if cfg.openai_api_key:
        out.success("API key saved")
    else:
        out.warn("No API key set — you can add it later in the config file")

    # Step 3: Data directory
    out.header("Step 3/3 · Data Directory")
    out.info("Where should context-use store its data?")
    out.info("This creates three subfolders:")
    out.info("  input/   — drop your .zip archives here")
    out.info("  output/  — exported memories and profiles")
    out.info("  storage/ — internal extracted archive data")
    print()
    data_dir = input(f"  Data directory [{cfg.data_dir}]: ").strip() or cfg.data_dir
    cfg.data_dir = data_dir
    cfg.ensure_dirs()
    out.success("Data directories created")

    # Save
    path = save_config(cfg)
    print()
    out.success(f"Config written to {path}")

    # Init store
    try:
        ctx = _build_ctx(cfg)
        await ctx.init()
        out.success("Store initialised")
    except Exception as exc:
        out.warn(f"Could not initialise store: {exc}")
        out.info("You can retry later with: context-use init")

    # Next steps
    out.header("You're all set! Next steps:")
    print()
    out.info(f"1. Drop your .zip exports into {out.bold(cfg.data_dir + '/input/')}")
    if cfg.store_provider == "memory":
        out.info("2. Run the full pipeline in one session:")
        out.next_step("context-use run")
        out.info("   Or directly:")
        out.next_step("context-use run chatgpt path/to/export.zip")
    else:
        out.info("2. Ingest them interactively:")
        out.next_step("context-use ingest")
        out.info("   Or directly:")
        out.next_step("context-use ingest instagram path/to/export.zip")
        out.info("3. Generate memories:")
        out.next_step("context-use memories generate")
        out.info("4. Generate your profile:")
        out.next_step("context-use profile generate")
    out.info(f"{'3' if cfg.store_provider == 'memory' else '5'}. Start the MCP server:")
    out.next_step("context-use server")
    print()


def _start_docker_postgres(cfg: Config) -> None:
    """Start a Postgres container via docker run."""
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


# ── run (ingest → memories → profile) ───────────────────────────────


async def cmd_run(args: argparse.Namespace) -> None:
    """Ingest an archive and run the full pipeline in one session.

    This is the recommended command for in-memory store usage, since
    each CLI invocation gets a fresh store.
    """
    from context_use import Provider

    cfg = load_config()
    _require_api_key(cfg)
    providers = _providers()

    if args.provider is None:
        picked = _pick_archive_interactive(cfg)
        if picked is None:
            return
        provider_str, zip_path = picked
    elif args.path is None:
        out.error("Please provide both provider and path, or omit both.")
        out.info("  Direct:      context-use run instagram export.zip")
        out.info("  Interactive:  context-use run")
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

    # Phase 2: Memories
    out.header("Phase 2/3 · Generating memories")
    out.info("Submitting batch jobs to OpenAI and polling for results...")
    print()

    mem_result = await ctx.generate_memories([result.archive_id])

    out.success("Memories generated")
    out.kv("Batches", mem_result.batches_created)

    count = await ctx.count_memories()
    out.kv("Active memories", f"{count:,}")
    print()

    if count == 0:
        out.warn("No memories generated — skipping profile")
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
    cfg.ensure_dirs()
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
    except EOFError, KeyboardInterrupt:
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
    _require_api_key(cfg)
    _warn_ephemeral(cfg)

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
    _require_api_key(cfg)
    _warn_ephemeral(cfg)

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
    _warn_ephemeral(cfg)

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
    _require_api_key(cfg)
    _warn_ephemeral(cfg)

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
    _warn_ephemeral(cfg)

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
    _require_api_key(cfg)
    _warn_ephemeral(cfg)

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
    out.next_step("context-use server", "start the MCP server")
    out.next_step('context-use ask "Tell me about myself"', "try the built-in agent")
    print()


# ── profile show ────────────────────────────────────────────────────


async def cmd_profile_show(args: argparse.Namespace) -> None:
    cfg = load_config()
    _warn_ephemeral(cfg)

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
    _warn_ephemeral(cfg)

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


# ── server ──────────────────────────────────────────────────────────


async def cmd_server(args: argparse.Namespace) -> None:
    cfg = load_config()

    out.header("Starting MCP server")
    print()

    ctx = _build_ctx(cfg)
    await ctx.init()

    try:
        from context_use.ext.mcp_use.server import create_server
    except ImportError:
        out.error(
            "MCP server requires extra dependencies.\n"
            "    Install them with: pip install context-use[mcp-use]"
        )
        sys.exit(1)

    server = create_server(ctx)

    transport = args.transport
    port = args.port

    if transport == "streamable-http":
        out.kv("Transport", "Streamable HTTP")
        out.kv("URL", f"http://localhost:{port}/mcp")
    else:
        out.kv("Transport", "stdio")

    print()
    out.info("Available tools:")
    out.info("  • get_profile — load the user's profile summary")
    out.info("  • search — search memories by query, date range, or both")

    if transport == "streamable-http":
        print()
        out.header("Connect your MCP client")
        print()
        out.info(out.bold("Claude Desktop") + " — add to claude_desktop_config.json:")
        print()
        print(
            out.dim(
                "    {\n"
                '      "mcpServers": {\n'
                '        "context-use": {\n'
                f'          "url": "http://localhost:{port}/mcp"\n'
                "        }\n"
                "      }\n"
                "    }"
            )
        )
        print()
        out.info(out.bold("Cursor") + " — add to .cursor/mcp.json:")
        print()
        print(
            out.dim(
                "    {\n"
                '      "mcpServers": {\n'
                '        "context-use": {\n'
                f'          "url": "http://localhost:{port}/mcp"\n'
                "        }\n"
                "      }\n"
                "    }"
            )
        )
    print()
    out.rule()

    kwargs: dict = {"transport": transport}
    if transport == "streamable-http":
        kwargs.update(host=args.host, port=port)

    server.run(**kwargs)  # pyright: ignore[reportAttributeAccessIssue]


# ── ask ─────────────────────────────────────────────────────────────


async def cmd_ask(args: argparse.Namespace) -> None:
    """Simple RAG agent: search memories + profile, then answer."""
    cfg = load_config()
    _require_api_key(cfg)
    _warn_ephemeral(cfg)

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
            except EOFError, KeyboardInterrupt:
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
            "Getting started:\n"
            "  context-use init                           Setup wizard\n"
            "  context-use run                            Full pipeline\n"
            "  context-use ingest                         Process archive\n"
            "  context-use memories generate              Generate memories\n"
            "  context-use profile generate               Create profile\n"
            "  context-use server                         Start MCP server\n"
            '  context-use ask "What did I do last week?" Ask a question\n'
        ),
    )
    sub = parser.add_subparsers(dest="command", title="commands")

    # init
    sub.add_parser("init", help="Interactive setup wizard")

    # ingest
    p_ingest = sub.add_parser(
        "ingest",
        help="Process a data export archive",
        description=(
            "Process a data export archive. Run without arguments to "
            "interactively pick from archives in data/input/."
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

    # run (ingest → memories → profile in one session)
    p_run = sub.add_parser(
        "run",
        help="Ingest + generate memories + profile in one session",
        description=(
            "Run the full pipeline (ingest, memories, profile) in a single "
            "process. Required for in-memory store; recommended for first-time use."
        ),
    )
    p_run.add_argument(
        "provider",
        nargs="?",
        choices=providers,
        default=None,
        help="Data provider (omit for interactive mode)",
    )
    p_run.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to .zip archive (omit for interactive mode)",
    )
    p_run.add_argument(
        "--skip-profile",
        action="store_true",
        help="Skip profile generation",
    )

    # memories
    p_mem = sub.add_parser("memories", help="Manage memories")
    mem_sub = p_mem.add_subparsers(dest="memories_command", title="memories commands")

    mem_sub.add_parser("generate", help="Generate memories from ingested archives")
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
    p_prof = sub.add_parser("profile", help="Manage your profile")
    prof_sub = p_prof.add_subparsers(dest="profile_command", title="profile commands")

    p_prof_gen = prof_sub.add_parser("generate", help="Generate or update your profile")
    p_prof_gen.add_argument(
        "--lookback",
        type=int,
        default=6,
        help="Lookback window in months (default: 6)",
    )

    prof_sub.add_parser("show", help="Display your current profile")

    p_prof_export = prof_sub.add_parser("export", help="Export profile to markdown")
    p_prof_export.add_argument("--out", metavar="PATH", help="Output file path")

    # server
    p_server = sub.add_parser("server", help="Start the MCP server")
    p_server.add_argument(
        "--transport",
        choices=["streamable-http", "stdio"],
        default="streamable-http",
        help="Transport protocol (default: streamable-http)",
    )
    p_server.add_argument("--host", default="0.0.0.0", help="Bind host")
    p_server.add_argument("--port", type=int, default=8000, help="Bind port")

    # ask
    p_ask = sub.add_parser("ask", help="Ask a question about your memories")
    p_ask.add_argument("query", nargs="?", help="Your question")
    p_ask.add_argument(
        "--interactive", action="store_true", help="Interactive chat mode"
    )

    return parser


# ── Dispatch ────────────────────────────────────────────────────────

_CommandHandler = Callable[[argparse.Namespace], Coroutine[Any, Any, None]]

_COMMAND_MAP: dict[str, _CommandHandler] = {
    "init": cmd_init,
    "ingest": cmd_ingest,
    "run": cmd_run,
    "server": cmd_server,
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


def main() -> None:
    import logging

    logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
    logging.getLogger("litellm").setLevel(logging.CRITICAL)

    parser = _build_parser()
    args = parser.parse_args()

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
    else:
        handler = _COMMAND_MAP.get(args.command)

    if handler is None:
        parser.print_help()
        return

    try:
        asyncio.run(handler(args))
    except KeyboardInterrupt:
        print()

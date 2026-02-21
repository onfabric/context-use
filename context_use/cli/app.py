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

PROVIDERS = ["instagram", "chatgpt"]


# ── Infrastructure helpers ──────────────────────────────────────────


def _build_db(cfg: Config):
    from context_use.db.postgres import PostgresBackend

    return PostgresBackend(
        host=cfg.db_host,
        port=cfg.db_port,
        database=cfg.db_name,
        user=cfg.db_user,
        password=cfg.db_password,
    )


def _build_storage(cfg: Config):
    from context_use.storage.disk import DiskStorage

    return DiskStorage(base_path=cfg.storage_path)


def _build_llm(cfg: Config):
    from context_use.llm import LLMClient, OpenAIEmbeddingModel, OpenAIModel

    return LLMClient(
        model=OpenAIModel.GPT_4O,
        api_key=cfg.openai_api_key,
        embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
    )


def _build_ctx(cfg: Config):
    from context_use import ContextUse

    return ContextUse(storage=_build_storage(cfg), db=_build_db(cfg))


def _require_api_key(cfg: Config) -> None:
    if not cfg.openai_api_key:
        out.error(
            "OpenAI API key not configured. "
            "Run 'context-use init' or set OPENAI_API_KEY."
        )
        sys.exit(1)


# ── init ────────────────────────────────────────────────────────────


async def cmd_init(args: argparse.Namespace) -> None:
    out.banner()
    print()
    out.info("This wizard will set up everything you need.\n")

    cfg = load_config() if config_exists() else Config()

    # Step 1: Database
    out.header("Step 1/3 · Database")
    out.info("context-use needs PostgreSQL with pgvector.")
    print()

    if shutil.which("docker") is None:
        out.warn(
            "Docker not found. Install Docker to auto-start Postgres,\n"
            "    or configure an existing Postgres instance."
        )
    else:
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
    out.success("Database configured")

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

    # Init DB
    try:
        db = _build_db(cfg)
        await db.init_db()
        out.success("Database tables created")
    except Exception as exc:
        out.warn(f"Could not initialise database: {exc}")
        out.info("You can retry later with: context-use init")

    # Next steps
    out.header("You're all set! Next steps:")
    print()
    out.info(f"1. Drop your .zip exports into {out.bold(cfg.data_dir + '/input/')}")
    out.info("2. Ingest them interactively:")
    out.next_step("context-use ingest")
    out.info("   Or directly:")
    out.next_step("context-use ingest instagram path/to/export.zip")
    out.info("3. Generate memories:")
    out.next_step("context-use memories generate")
    out.info("4. Generate your profile:")
    out.next_step("context-use profile generate")
    out.info("5. Start the MCP server:")
    out.next_step("context-use server")
    print()


def _start_docker_postgres(cfg: Config) -> None:
    """Start a Postgres container via docker run."""
    container_name = "context-use-postgres"

    # Check if already running
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and "true" in result.stdout:
        out.success("Postgres container already running")
        return

    # Remove stopped container if it exists
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
    for provider in PROVIDERS:
        if provider in name:
            return provider
    return None


def _pick_archive_interactive(cfg: Config) -> tuple[str, str] | None:
    """Interactive picker: list archives in data/input, let user choose."""
    cfg.ensure_dirs()
    archives = _scan_input_dir(cfg.input_dir)

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

    # Pick archive
    choice = input(f"  Which archive? [1-{len(archives)}]: ").strip()
    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(archives)):
            raise ValueError
    except ValueError:
        out.error("Invalid choice.")
        return None

    selected = archives[idx]

    # Pick provider
    guessed = _guess_provider(selected.name)
    if guessed:
        confirm = input(f"  Provider? [{guessed}]: ").strip().lower()
        provider_str = confirm if confirm else guessed
    else:
        provider_str = input(f"  Provider ({', '.join(PROVIDERS)}): ").strip().lower()

    if provider_str not in PROVIDERS:
        choices = ", ".join(PROVIDERS)
        out.error(f"Unknown provider '{provider_str}'. Choose from: {choices}")
        return None

    return provider_str, str(selected)


async def cmd_ingest(args: argparse.Namespace) -> None:
    cfg = load_config()

    # Interactive mode: no provider/path given
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

        if provider_str not in PROVIDERS:
            choices = ", ".join(PROVIDERS)
            out.error(f"Unknown provider '{provider_str}'. Choose from: {choices}")
            sys.exit(1)

        if not Path(zip_path).exists():
            out.error(f"File not found: {zip_path}")
            sys.exit(1)

    from context_use.providers.registry import Provider

    provider = Provider(provider_str)

    print()
    out.header(f"Ingesting {provider.value} archive")
    out.kv("File", zip_path)
    out.kv("Provider", provider.value)
    print()

    ctx = _build_ctx(cfg)
    db = _build_db(cfg)
    await db.init_db()

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

    # Show per-interaction-type breakdown
    from sqlalchemy import select

    from context_use.etl.models.etl_task import EtlTask

    session = db.get_session()
    try:
        stmt = select(EtlTask).where(EtlTask.archive_id == result.archive_id)
        tasks = list((await session.execute(stmt)).scalars().all())
        if tasks:
            print()
            out.info("Breakdown:")
            for t in tasks:
                label = t.interaction_type.replace("_", " ").title()
                out.kv(
                    label,
                    f"{t.uploaded_count:,} threads",
                    indent=4,
                )
    finally:
        await session.close()

    print()
    out.header("Next step:")
    out.next_step("context-use memories generate")
    print()


# ── memories generate ───────────────────────────────────────────────


async def cmd_memories_generate(args: argparse.Namespace) -> None:
    cfg = load_config()
    _require_api_key(cfg)

    from sqlalchemy import func, select

    from context_use.etl.models.archive import Archive, ArchiveStatus
    from context_use.etl.models.etl_task import EtlTask
    from context_use.etl.models.thread import Thread

    db = _build_db(cfg)
    ctx = _build_ctx(cfg)
    llm = _build_llm(cfg)

    # Fetch completed archives with thread counts
    session = db.get_session()
    try:
        stmt = (
            select(
                Archive.id,
                Archive.provider,
                Archive.created_at,
                func.count(Thread.id).label("thread_count"),
            )
            .where(Archive.status == ArchiveStatus.COMPLETED.value)
            .outerjoin(EtlTask, EtlTask.archive_id == Archive.id)
            .outerjoin(Thread, Thread.etl_task_id == EtlTask.id)
            .group_by(Archive.id, Archive.provider, Archive.created_at)
            .order_by(Archive.created_at)
        )
        rows = (await session.execute(stmt)).all()
    finally:
        await session.close()

    if not rows:
        out.warn("No completed archives found. Run 'context-use ingest' first.")
        return

    # Let user pick one
    out.header("Completed archives")
    print()
    for i, (aid, provider, created_at, thread_count) in enumerate(rows, 1):
        ts = created_at.strftime("%Y-%m-%d %H:%M")
        print(
            f"  {out.bold(str(i))}. {provider}"
            f"  {out.dim(f'{thread_count} threads')}"
            f"  {out.dim(ts)}"
            f"  {out.dim(aid[:8])}"
        )
    print()

    try:
        choice = input(f"  Which archive? [1-{len(rows)}]: ").strip()
    except EOFError, KeyboardInterrupt:
        print()
        return

    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(rows)):
            raise ValueError
    except ValueError:
        out.error("Invalid choice.")
        return

    selected_id = rows[idx][0]
    selected_provider = rows[idx][1]

    out.header("Generating memories")
    out.info("This submits batch jobs to OpenAI and polls for results.")
    out.info("It typically takes 2-10 minutes depending on data volume.\n")
    out.kv("Archive", f"{selected_provider} ({selected_id[:8]})")

    result = await ctx.generate_memories([selected_id], llm)

    out.success("Memories generated")
    out.kv("Tasks processed", result.tasks_processed)
    out.kv("Batches created", result.batches_created)
    if result.errors:
        for e in result.errors:
            out.error(e)

    # Show summary
    from context_use.memories.models import MemoryStatus, TapestryMemory

    session = db.get_session()
    try:
        stmt = select(TapestryMemory).where(
            TapestryMemory.status == MemoryStatus.active.value
        )
        memories = list((await session.execute(stmt)).scalars().all())
    finally:
        await session.close()

    if memories:
        memories.sort(key=lambda m: m.from_date)
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
    out.next_step("context-use profile generate", "create your profile")
    out.next_step("context-use memories list", "browse your memories")
    out.next_step("context-use memories export", "export to markdown")
    print()


# ── memories list ───────────────────────────────────────────────────


async def cmd_memories_list(args: argparse.Namespace) -> None:
    cfg = load_config()

    from sqlalchemy import func, select

    from context_use.memories.models import MemoryStatus, TapestryMemory

    db = _build_db(cfg)
    session = db.get_session()
    try:
        stmt = (
            select(TapestryMemory)
            .where(TapestryMemory.status == MemoryStatus.active.value)
            .order_by(TapestryMemory.from_date)
        )
        if args.limit:
            stmt = stmt.limit(args.limit)
        memories = list((await session.execute(stmt)).scalars().all())

        count_stmt = (
            select(func.count())
            .select_from(TapestryMemory)
            .where(TapestryMemory.status == MemoryStatus.active.value)
        )
        total = (await session.execute(count_stmt)).scalar() or 0
    finally:
        await session.close()

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

    from context_use.search.memories import search_memories

    db = _build_db(cfg)

    from_date = date.fromisoformat(args.from_date) if args.from_date else None
    to_date = date.fromisoformat(args.to_date) if args.to_date else None

    results = await search_memories(
        db,
        query=args.query,
        from_date=from_date,
        to_date=to_date,
        top_k=args.top_k,
        openai_api_key=cfg.openai_api_key,
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

    from sqlalchemy import select

    from context_use.memories.models import MemoryStatus, TapestryMemory

    db = _build_db(cfg)
    session = db.get_session()
    try:
        stmt = (
            select(TapestryMemory)
            .where(TapestryMemory.status == MemoryStatus.active.value)
            .order_by(TapestryMemory.from_date)
        )
        memories = list((await session.execute(stmt)).scalars().all())
    finally:
        await session.close()

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

    out.header("Generating profile")

    from sqlalchemy import func, select

    from context_use.memories.models import MemoryStatus, TapestryMemory
    from context_use.profile.generator import generate_profile
    from context_use.profile.models import TapestryProfile  # noqa: F401

    db = _build_db(cfg)
    llm = _build_llm(cfg)

    session = db.get_session()
    try:
        # Ensure tables exist
        from context_use.etl.models.base import Base

        async with db.get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        count = (
            await session.execute(
                select(func.count()).where(
                    TapestryMemory.status == MemoryStatus.active.value,
                )
            )
        ).scalar() or 0

        if count == 0:
            out.warn("No memories found. Run 'context-use memories generate' first.")
            return

        out.kv("Active memories", f"{count:,}")
        out.kv("Lookback", f"{args.lookback} months")
        print()

        profile = await generate_profile(
            None,
            session,
            llm,
            lookback_months=args.lookback,
        )
        await session.commit()
    finally:
        await session.close()

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

    from sqlalchemy import select

    from context_use.profile.models import TapestryProfile

    db = _build_db(cfg)

    # Ensure tables exist
    from context_use.etl.models.base import Base

    async with db.get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session = db.get_session()
    try:
        result = await session.execute(
            select(TapestryProfile)
            .order_by(TapestryProfile.generated_at.desc())
            .limit(1)
        )
        profile = result.scalar_one_or_none()
    finally:
        await session.close()

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

    from sqlalchemy import select

    from context_use.profile.models import TapestryProfile

    db = _build_db(cfg)

    from context_use.etl.models.base import Base

    async with db.get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session = db.get_session()
    try:
        result = await session.execute(
            select(TapestryProfile)
            .order_by(TapestryProfile.generated_at.desc())
            .limit(1)
        )
        profile = result.scalar_one_or_none()
    finally:
        await session.close()

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

    db = _build_db(cfg)
    api_key = cfg.openai_api_key or None

    try:
        from context_use.ext.mcp_use.server import create_server
    except ImportError:
        out.error(
            "MCP server requires extra dependencies.\n"
            "    Install them with: pip install context-use[mcp-use]"
        )
        sys.exit(1)

    server = create_server(db=db, openai_api_key=api_key)

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

    server.run(**kwargs)


# ── ask ─────────────────────────────────────────────────────────────


async def cmd_ask(args: argparse.Namespace) -> None:
    """Simple RAG agent: search memories + profile, then answer."""
    cfg = load_config()
    _require_api_key(cfg)

    db = _build_db(cfg)

    from context_use.etl.models.base import Base

    async with db.get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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

        answer = await _answer_query(query, db, cfg)
        print(f"\n{answer}\n")

        if not interactive:
            break


async def _answer_query(query: str, db, cfg: Config) -> str:
    """Build context from profile + memories, then call the LLM."""
    from sqlalchemy import select

    from context_use.profile.models import TapestryProfile
    from context_use.search.memories import search_memories

    # Gather context
    session = db.get_session()
    try:
        result = await session.execute(
            select(TapestryProfile)
            .order_by(TapestryProfile.generated_at.desc())
            .limit(1)
        )
        profile = result.scalar_one_or_none()
    finally:
        await session.close()

    results = await search_memories(
        db,
        query=query,
        top_k=10,
        openai_api_key=cfg.openai_api_key,
    )

    # Build prompt
    parts: list[str] = []
    parts.append(
        "You are a helpful assistant with access to the user's personal "
        "memories and profile. Answer their question based on the context "
        "below. Be specific and reference dates/details from the memories. "
        "If the context doesn't contain enough information, say so honestly."
    )

    if profile:
        parts.append(f"\n## User Profile\n\n{profile.content}")

    if results:
        parts.append("\n## Relevant Memories\n")
        for r in results:
            parts.append(f"- [{r.from_date}] {r.content}")

    parts.append(f"\n## Question\n\n{query}")

    prompt = "\n".join(parts)

    llm = _build_llm(cfg)
    return await llm.completion(prompt)


# ── Parser ──────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-use",
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Getting started:\n"
            "  context-use init                                Setup wizard\n"
            "  context-use ingest                              Pick & process archive\n"
            "  context-use memories generate                   Generate memories\n"
            "  context-use profile generate                    Create your profile\n"
            "  context-use server                              Start MCP server\n"
            '  context-use ask "What did I do last week?"      Ask a question\n'
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
        choices=PROVIDERS,
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
    p_mem = sub.add_parser("memories", help="Manage memories")
    mem_sub = p_mem.add_subparsers(dest="memories_command", title="memories commands")

    mem_sub.add_parser("generate", help="Generate memories from ingested archives")

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
        "--lookback", type=int, default=6, help="Lookback window in months (default: 6)"
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
    "server": cmd_server,
    "ask": cmd_ask,
}

_MEMORIES_MAP: dict[str, _CommandHandler] = {
    "generate": cmd_memories_generate,
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

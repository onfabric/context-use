from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from context_use.cli import output as out
from context_use.cli.base import (
    EphemeralApiCommand,
    PersistentApiCommand,
    add_archive_args,
    print_ingest_result,
    resolve_archive,
    run_batches,
)
from context_use.cli.commands.memories import (
    export_memories_json,
    export_memories_markdown,
)
from context_use.cli.config import Config

if TYPE_CHECKING:
    from context_use import ContextUse


# ── quickstart ───────────────────────────────────────────────────────────────


class QuickstartCommand(EphemeralApiCommand):
    name = "quickstart"
    help = "Try it out — ingest + memories in one session (no database needed)"
    description = (
        "Run the full pipeline (ingest, memories) in one session "
        "using the real-time API. No database needed. "
        "By default processes the last 30 days; use --full for all history."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_archive_args(parser)
        parser.add_argument(
            "--full",
            action="store_true",
            help="Process full archive history (default: last 30 days)",
        )
        parser.add_argument(
            "--last-days",
            type=int,
            default=30,
            help="Only process threads from the last N days (default: 30)",
        )

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        from context_use import Provider

        picked = resolve_archive(args, cfg, command="quickstart")
        if picked is None:
            return
        provider_str, zip_path = picked

        full = args.full
        since = None if full else datetime.now(UTC) - timedelta(days=args.last_days)

        if full and sys.stdin.isatty():
            print()
            out.warn(
                "Processing the full archive with the real-time API. "
                "Large archives may hit OpenAI rate limits and take "
                "significantly longer."
            )
            out.info(
                "For large archives, consider using PostgreSQL with the batch API:"
            )
            out.next_step("context-use config set-store postgres")
            print()
            confirm = input("  Continue? [y/N] ").strip().lower()
            if confirm not in ("y", "yes"):
                out.info("Aborted.")
                return

        provider = Provider(provider_str)

        # Phase 1: Ingest
        print()
        out.header(f"Phase 1/2 · Ingesting {provider.value} archive")
        out.kv("File", zip_path)
        print()

        result = await ctx.process_archive(provider, zip_path)

        out.success("Archive processed")
        print_ingest_result(result)
        print()

        if result.tasks_failed:
            out.error(f"{result.tasks_failed} tasks failed — stopping")
            return

        # Phase 2: Memories (real-time API)
        out.header("Phase 2/2 · Generating memories")
        out.info("Using real-time API.")
        if since:
            out.kv("Since", since.strftime("%Y-%m-%d"))
            out.info(f"Only processing the last {args.last_days} days as a preview.")
        else:
            out.info("Processing full archive history.")
        print()

        batches = await ctx.create_memory_batches(since=since)
        await run_batches(ctx, batches)

        out.success("Memories generated")
        out.kv("Batches", len(batches))

        count = await ctx.count_memories()
        out.kv("Active memories", f"{count:,}")
        print()

        if count == 0:
            if not full:
                print()
                out.info("Try including more history:")
                out.next_step(
                    f"context-use quickstart --last-days 90 {provider.value} {zip_path}"
                )
                out.info("Or process the full archive:")
                out.next_step(
                    f"context-use quickstart --full {provider.value} {zip_path}"
                )
            return

        # Show a preview of the memories
        memories = await ctx.list_memories()
        if memories:
            out.header(f"Your memories ({len(memories):,})")
            print()
            for m in memories[:10]:
                print(f"  [{m.from_date.isoformat()}] {m.content}")
            if len(memories) > 10:
                out.info(f"  ... and {len(memories) - 10:,} more")
            print()

        # Export to files
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        exported: list[str] = []

        if memories:
            md_path = cfg.output_dir / f"memories_{ts}.md"
            export_memories_markdown(memories, md_path)
            json_path = cfg.output_dir / f"memories_{ts}.json"
            export_memories_json(memories, json_path)
            exported.append(f"Memories  → {md_path}")
            exported.append(f"           {json_path}")

        if exported:
            out.header("Exported")
            for line in exported:
                out.success(line)
            print()

        out.success("Pipeline complete!")

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


# ── pipeline ─────────────────────────────────────────────────────────────────


class PipelineCommand(PersistentApiCommand):
    """Ingest + memories using PostgreSQL and the batch API.

    This is the production path for large archives. Uses the OpenAI Batch
    API for memory generation — cheaper and rate-limit-friendly compared to
    the real-time API used by ``quickstart``.
    """

    name = "pipeline"
    help = "Full pipeline — ingest + memories (requires PostgreSQL)"
    description = (
        "Run the full pipeline (ingest, memories) using PostgreSQL "
        "and the batch API. Run without arguments to interactively pick an "
        "archive from data/input/."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_archive_args(parser)

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        from context_use import Provider

        picked = resolve_archive(args, cfg, command="pipeline")
        if picked is None:
            return
        provider_str, zip_path = picked

        provider = Provider(provider_str)

        # Step 1: Ingest
        print()
        out.header(f"Step 1/2 · Ingesting {provider.value} archive")
        out.kv("File", zip_path)
        print()

        result = await ctx.process_archive(provider, zip_path)

        out.success("Archive processed")
        print_ingest_result(result)
        print()

        if result.tasks_failed:
            out.error(f"{result.tasks_failed} tasks failed — stopping")
            return

        # Step 2: Memories (batch API)
        out.header("Step 2/2 · Generating memories")
        out.info("Using batch API. This typically takes 2-10 minutes.\n")

        batches = await ctx.create_memory_batches()
        await run_batches(ctx, batches)

        out.success("Memories generated")
        out.kv("Batches created", len(batches))

        count = await ctx.count_memories()
        out.kv("Active memories", f"{count:,}")
        print()

        if count == 0:
            return

        out.success("Pipeline complete!")
        print()
        out.header("What's next:")
        out.next_step("context-use memories list", "browse your memories")
        out.next_step('context-use memories search "query"', "semantic search")
        out.next_step(
            'context-use ask "Tell me about myself"', "try the built-in agent"
        )
        out.next_step("python -m context_use.ext.mcp_use.run", "start the MCP server")
        print()

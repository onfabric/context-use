from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from context_use.cli import output as out
from context_use.cli.base import (
    ApiCommand,
    add_archive_args,
    print_ingest_result,
    resolve_archive,
    run_batches,
)
from context_use.cli.commands.memories import (
    export_memories_json,
    export_memories_markdown,
)
from context_use.config import Config

if TYPE_CHECKING:
    from context_use import ContextUse


_QUICK_DEFAULT_DAYS = 30


class PipelineCommand(ApiCommand):
    name = "pipeline"
    help = "Full pipeline — ingest + memories"
    description = (
        "Run the full pipeline (ingest, memories). "
        "Uses the batch API by default. "
        "Pass --quick to use the real-time API "
        "(last 30 days from latest data point by default). "
        "Use --last-days to limit history in either mode. "
        "Run without arguments to interactively pick an archive from "
        "data/input/."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_archive_args(parser)
        parser.add_argument(
            "--quick",
            action="store_true",
            help="Use the real-time API (default: last 30 days from latest data point)",
        )
        parser.add_argument(
            "--last-days",
            type=int,
            default=None,
            help=(
                "Only process threads from the last N days "
                "(counted back from latest thread date; "
                "default: 30 with --quick, unlimited otherwise)"
            ),
        )

    def _prepare(self, cfg: Config, args: argparse.Namespace) -> Config:
        cfg = super()._prepare(cfg, args)
        if getattr(args, "quick", False):
            self.llm_mode = "sync"  # type: ignore[misc]
        return cfg

    def _resolve_since(
        self,
        args: argparse.Namespace,
        latest_thread_asat: datetime | None,
    ) -> datetime | None:
        last_days = args.last_days
        if last_days is None:
            last_days = _QUICK_DEFAULT_DAYS if args.quick else None
        if last_days is None:
            return None
        if latest_thread_asat is None:
            return None
        return latest_thread_asat - timedelta(days=last_days)

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        picked = resolve_archive(args, cfg, command="pipeline")
        if picked is None:
            return
        provider_str, zip_path = picked

        if args.quick:
            await self._run_quick(cfg, ctx, args, provider_str, zip_path)
        else:
            await self._run_batch(ctx, args, provider_str, zip_path)

    async def _run_batch(
        self,
        ctx: ContextUse,
        args: argparse.Namespace,
        provider_str: str,
        zip_path: str,
    ) -> None:
        print()
        out.header(f"Step 1/2 · Ingesting {provider_str} archive")
        out.kv("File", zip_path)
        print()

        result = await ctx.process_archive(provider_str, zip_path)

        out.success("Archive processed")
        print_ingest_result(result)
        print()

        if result.tasks_failed:
            out.error(f"{result.tasks_failed} tasks failed — stopping")
            return

        latest_thread_asat = await ctx.get_latest_memory_thread_asat()
        since = self._resolve_since(args, latest_thread_asat)

        out.header("Step 2/2 · Generating memories")
        out.info("Using batch API. This typically takes 2-10 minutes.")
        if since:
            out.kv("Since", since.strftime("%Y-%m-%d"))
            if latest_thread_asat is not None:
                out.info(
                    "Window is counted back from latest thread date "
                    f"({latest_thread_asat.strftime('%Y-%m-%d')})."
                )
        print()

        batches = await ctx.create_memory_batches(since=since)
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
        print()

    async def _run_quick(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
        provider_str: str,
        zip_path: str,
    ) -> None:
        last_days = (
            args.last_days if args.last_days is not None else _QUICK_DEFAULT_DAYS
        )

        # Phase 1: Ingest
        print()
        out.header(f"Phase 1/2 · Ingesting {provider_str} archive")
        out.kv("File", zip_path)
        print()

        result = await ctx.process_archive(provider_str, zip_path)

        out.success("Archive processed")
        print_ingest_result(result)
        print()

        if result.tasks_failed:
            out.error(f"{result.tasks_failed} tasks failed — stopping")
            return

        latest_thread_asat = await ctx.get_latest_memory_thread_asat()
        since = self._resolve_since(args, latest_thread_asat)

        # Phase 2: Memories (real-time API)
        out.header("Phase 2/2 · Generating memories")
        out.info("Using real-time API.")
        if since:
            out.kv("Since", since.strftime("%Y-%m-%d"))
            if latest_thread_asat is not None:
                out.info(
                    f"Only processing the last {last_days} days "
                    "from latest thread date "
                    f"({latest_thread_asat.strftime('%Y-%m-%d')})."
                )
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
            if since:
                print()
                out.info("Try including more history:")
                out.next_step(
                    f"context-use pipeline --quick --last-days 90 "
                    f"{provider_str} {zip_path}"
                )
            return

        memories = await ctx.list_memories()
        if memories:
            out.header(f"Your memories ({len(memories):,})")
            print()
            for m in memories[:10]:
                print(f"  [{m.from_date.isoformat()}] {m.content}")
            if len(memories) > 10:
                out.info(f"  ... and {len(memories) - 10:,} more")
            print()

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
        out.info("Run the full pipeline with the batch API:")
        out.next_step("context-use pipeline")
        print()
        out.info("Or explore your memories:")
        out.next_step("context-use memories list", "browse your memories")
        out.next_step('context-use memories search "query"', "semantic search")
        print()

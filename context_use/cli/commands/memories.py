from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from itertools import groupby
from pathlib import Path
from typing import TYPE_CHECKING

from context_use.cli import output as out

if TYPE_CHECKING:
    from context_use import ContextUse
    from context_use.facade.types import MemorySummary
from context_use.cli.base import (
    CommandGroup,
    PersistentApiCommand,
    PersistentCommand,
    run_batches,
)
from context_use.cli.config import Config

# ── Export helpers ────────────────────────────────────────────────────────────


def export_memories_markdown(memories: list[MemorySummary], path: Path) -> None:
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


def export_memories_json(memories: list[MemorySummary], path: Path) -> None:
    rows = [
        {
            "content": m.content,
            "from_date": m.from_date.isoformat(),
            "to_date": m.to_date.isoformat(),
        }
        for m in memories
    ]
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


# ── generate ─────────────────────────────────────────────────────────────────


class MemoriesGenerateCommand(PersistentApiCommand):
    name = "generate"
    display_name = "memories generate"
    help = "Step 2: Generate memories from ingested archives (batch API)"

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        out.header("Generating memories")
        out.info("Processes all unprocessed threads across all archives.")
        out.info("This submits batch jobs to OpenAI and polls for results.")
        out.info("It typically takes 2-10 minutes depending on data volume.\n")

        batches = await ctx.create_memory_batches()
        await run_batches(ctx, batches)

        out.success("Memories generated")
        out.kv("Batches created", len(batches))

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
        out.next_step("context-use memories list", "browse your memories")
        out.next_step("context-use memories export", "export to markdown")
        print()


# ── list ─────────────────────────────────────────────────────────────────────


class MemoriesListCommand(PersistentCommand):
    name = "list"
    display_name = "memories list"
    help = "List memories"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--limit", type=int, default=None, help="Max memories to show"
        )

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
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
                print(f"    [{m.from_date.isoformat()}] {m.content}")
            print()


# ── search ───────────────────────────────────────────────────────────────────


class MemoriesSearchCommand(PersistentApiCommand):
    name = "search"
    display_name = "memories search"
    help = "Semantic search over memories"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("query", nargs="?", help="Semantic search query")
        parser.add_argument("--from", dest="from_date", help="Start date (YYYY-MM-DD)")
        parser.add_argument("--to", dest="to_date", help="End date (YYYY-MM-DD)")
        parser.add_argument("--top-k", type=int, default=10, help="Number of results")

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
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
            sim = (
                f"  {out.dim(f'similarity={r.similarity:.4f}')}"
                if r.similarity is not None
                else ""
            )
            print(f"  {i}. [{r.from_date}]{sim}")
            print(f"     {r.content}")
        print()


# ── export ───────────────────────────────────────────────────────────────────


class MemoriesExportCommand(PersistentCommand):
    name = "export"
    display_name = "memories export"
    help = "Export memories to a file"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--format",
            choices=["markdown", "json"],
            default="markdown",
            help="Output format (default: markdown)",
        )
        parser.add_argument("--out", metavar="PATH", help="Output file path")

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
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
            export_memories_markdown(memories, out_path)
        else:
            export_memories_json(memories, out_path)

        out.success(f"Exported {len(memories):,} memories to {out_path}")


# ── group ─────────────────────────────────────────────────────────────────────


class MemoriesGroup(CommandGroup):
    name = "memories"
    help = "Manage memories (requires PostgreSQL)"
    subcommands = [
        MemoriesGenerateCommand,
        MemoriesListCommand,
        MemoriesSearchCommand,
        MemoriesExportCommand,
    ]


import argparse
import json
from datetime import UTC, date, datetime
from itertools import groupby
from pathlib import Path
from typing import TYPE_CHECKING

from context_use.cli import output as out

if TYPE_CHECKING:
    from context_use import ContextUse
    from context_use.models.memory import MemorySummary

from context_use.cli.base import (
    ApiCommand,
    CommandGroup,
    ContextCommand,
    run_batches,
)
from context_use.config import Config


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


class MemoriesGenerateCommand(ApiCommand):
    name = "generate"
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


class MemoriesListCommand(ContextCommand):
    name = "list"
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


class MemoriesSearchCommand(ApiCommand):
    name = "search"
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


class MemoriesGetCommand(ContextCommand):
    name = "get"
    help = "Show full details of a single memory"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", help="Memory UUID")

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        m = await ctx.get_memory(args.id)
        if m is None:
            out.warn(f"Memory {args.id!r} not found.")
            return

        out.header("Memory")
        print()
        out.kv("ID", m.id)
        out.kv("Status", m.status)
        out.kv("Date range", f"{m.from_date.isoformat()} – {m.to_date.isoformat()}")
        if m.source_memory_ids:
            out.kv("Sources", ", ".join(m.source_memory_ids))
        print()
        print(m.content)
        print()


class MemoriesUpdateCommand(ApiCommand):
    name = "update"
    help = "Edit the content or date range of a memory"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", help="Memory UUID")
        parser.add_argument("--content", help="New content text")
        parser.add_argument(
            "--from", dest="from_date", help="New start date (YYYY-MM-DD)"
        )
        parser.add_argument("--to", dest="to_date", help="New end date (YYYY-MM-DD)")

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        if not any([args.content, args.from_date, args.to_date]):
            out.warn("Provide at least one of --content, --from, or --to.")
            return

        from_dt = date.fromisoformat(args.from_date) if args.from_date else None
        to_dt = date.fromisoformat(args.to_date) if args.to_date else None

        try:
            m = await ctx.update_memory(
                args.id,
                content=args.content,
                from_date=from_dt,
                to_date=to_dt,
            )
        except ValueError as exc:
            out.warn(str(exc))
            return

        out.success(f"Updated memory {m.id}")


class MemoriesCreateCommand(ApiCommand):
    name = "create"
    help = "Write a new memory to the store"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--content", required=True, help="Memory text")
        parser.add_argument(
            "--from", dest="from_date", required=True, help="Start date (YYYY-MM-DD)"
        )
        parser.add_argument(
            "--to", dest="to_date", required=True, help="End date (YYYY-MM-DD)"
        )
        parser.add_argument(
            "--source",
            dest="source_ids",
            nargs="+",
            metavar="ID",
            help="Source memory IDs (for pattern/merge memories)",
        )

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        m = await ctx.create_memory(
            content=args.content,
            from_date=date.fromisoformat(args.from_date),
            to_date=date.fromisoformat(args.to_date),
            source_memory_ids=args.source_ids,
        )
        out.success(f"Created memory {m.id}")


class MemoriesArchiveCommand(ContextCommand):
    name = "archive"
    help = "Mark one or more memories as superseded"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "ids", nargs="+", metavar="ID", help="Memory UUIDs to archive"
        )
        parser.add_argument(
            "--superseded-by",
            metavar="ID",
            help="ID of the memory that replaces these",
        )

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        archived = await ctx.archive_memories(
            args.ids, superseded_by=args.superseded_by
        )
        not_found = [mid for mid in args.ids if mid not in set(archived)]

        if archived:
            out.success(
                f"Archived {len(archived)} memor{'y' if len(archived) == 1 else 'ies'}"
            )
        if not_found:
            out.warn(f"Not found: {', '.join(not_found)}")


class MemoriesExportCommand(ContextCommand):
    name = "export"
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


class MemoriesGroup(CommandGroup):
    name = "memories"
    help = "Manage memories"
    subcommands = [
        MemoriesGenerateCommand,
        MemoriesListCommand,
        MemoriesSearchCommand,
        MemoriesGetCommand,
        MemoriesUpdateCommand,
        MemoriesCreateCommand,
        MemoriesArchiveCommand,
        MemoriesExportCommand,
    ]

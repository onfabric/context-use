from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from context_use.cli import output as out
from context_use.cli.base import ApiCommand
from context_use.cli.config import Config

if TYPE_CHECKING:
    from context_use import ContextUse


class SearchCommand(ApiCommand):
    name = "search"
    help = "Semantic search over embedded threads"
    description = (
        "Search thread embeddings by semantic similarity. "
        "Requires that 'embed' has been run first."
    )
    llm_mode = "sync"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("query", help="Semantic search query")
        parser.add_argument(
            "--top-k", type=int, default=10, help="Number of results (default: 10)"
        )
        parser.add_argument(
            "--interaction-types",
            type=str,
            default=None,
            help="Comma-separated list of interaction types to filter by",
        )

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        interaction_types: list[str] | None = None
        if args.interaction_types:
            interaction_types = [t.strip() for t in args.interaction_types.split(",")]

        results = await ctx.search_threads(
            query=args.query,
            top_k=args.top_k,
            interaction_types=interaction_types,
        )

        if not results:
            out.warn("No matching threads found.")
            return

        out.header(f"Search results ({len(results)})")
        print()
        for i, r in enumerate(results, 1):
            sim = out.dim(f"similarity={r.similarity:.4f}")
            ts = r.asat.strftime("%Y-%m-%d %H:%M")
            print(f"  {i}. [{r.interaction_type}] {ts}  {sim}")
            preview = r.content[:200].replace("\n", " ")
            if len(r.content) > 200:
                preview += "…"
            print(f"     {preview}")
        print()

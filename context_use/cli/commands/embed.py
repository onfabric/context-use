from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from context_use.cli import output as out
from context_use.cli.base import ApiCommand, create_batch_reporter, run_batches
from context_use.cli.config import Config

if TYPE_CHECKING:
    from context_use import ContextUse


class EmbedCommand(ApiCommand):
    name = "embed"
    help = "Embed thread content for semantic search"
    description = (
        "Generate vector embeddings for all unprocessed threads. "
        "Asset threads require descriptions first (run 'describe' beforehand). "
        "Use --last-days or --since to limit the date range."
    )
    llm_mode = "batch"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--last-days",
            type=int,
            default=None,
            help="Only process threads from the last N days",
        )
        parser.add_argument(
            "--since",
            type=str,
            default=None,
            help="Only process threads after this date (YYYY-MM-DD)",
        )

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        since = self._resolve_since(args)

        out.header("Embedding threads")
        out.info("Embeds all threads that have not been embedded yet.")
        if since:
            out.kv("Since", since.strftime("%Y-%m-%d"))
        print()

        batches = await ctx.create_thread_embedding_batches(since=since)

        if not batches:
            out.info("No threads to embed.")
            return

        await run_batches(
            ctx,
            batches,
            reporter_factory=create_batch_reporter,
        )

        out.success("Thread embeddings generated")
        out.kv("Batches", len(batches))
        print()

    def _resolve_since(self, args: argparse.Namespace) -> datetime | None:
        if args.since:
            return datetime.fromisoformat(args.since).replace(tzinfo=UTC)
        if args.last_days is not None:
            return datetime.now(UTC) - timedelta(days=args.last_days)
        return None

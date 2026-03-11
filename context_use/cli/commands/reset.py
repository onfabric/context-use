from __future__ import annotations

import argparse

from context_use.cli import output as out
from context_use.cli.base import BaseCommand
from context_use.config import build_ctx, load_config


class ResetCommand(BaseCommand):
    """Wipe all stored data and recreate the store schema.

    Intentionally does NOT use ContextCommand — ``ctx.reset()`` is called
    directly, bypassing ``ctx.init()``, to avoid creating the schema before
    immediately dropping it.
    """

    name = "reset"
    help = "Wipe all stored data"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--yes",
            "-y",
            action="store_true",
            help="Skip confirmation prompt",
        )

    async def execute(self, args: argparse.Namespace) -> None:
        cfg = load_config()

        print()
        out.header("Reset store")
        out.warn("This will permanently delete ALL data.")
        print()

        if not args.yes:
            confirm = input("  Type 'yes' to confirm: ").strip().lower()
            if confirm != "yes":
                out.info("Aborted.")
                return

        ctx = build_ctx(cfg)
        await ctx.reset()
        out.success("All data deleted.")
        print()

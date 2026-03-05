from __future__ import annotations

import argparse

from context_use.cli import output as out
from context_use.cli.base import BaseCommand, build_ctx, require_persistent
from context_use.cli.config import load_config


class ResetCommand(BaseCommand):
    """Wipe all stored data and recreate the store schema.

    Intentionally does NOT use PersistentCommand — ``ctx.reset()`` is called
    directly, bypassing ``ctx.init()``, to avoid creating the schema before
    immediately dropping it.
    """

    name = "reset"
    help = "Wipe all stored data (requires PostgreSQL)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--yes",
            "-y",
            action="store_true",
            help="Skip confirmation prompt",
        )

    async def execute(self, args: argparse.Namespace) -> None:
        cfg = load_config()
        require_persistent(cfg, "reset")

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

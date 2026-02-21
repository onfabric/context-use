# /// script
# requires-python = ">=3.12"
# dependencies = ["context_use[disk]"]
# [tool.uv.sources]
# context_use = { path = ".", editable = true }
# ///

"""Quick start demo for context_use.

Usage:
    uv run quickstart.py --chatgpt ~/downloads/chatgpt-export.zip
    uv run quickstart.py --instagram ~/downloads/instagram-export.zip
    uv run quickstart.py --chatgpt ~/chatgpt.zip --instagram ~/instagram.zip
"""

import argparse
import asyncio

from context_use import ContextUse
from context_use.providers.registry import Provider

parser = argparse.ArgumentParser(description="contextuse quickstart")
parser.add_argument("--chatgpt", metavar="PATH", help="Path to a ChatGPT export zip")
parser.add_argument(
    "--instagram", metavar="PATH", help="Path to an Instagram export zip"
)
args = parser.parse_args()

if not args.chatgpt and not args.instagram:
    parser.error("provide at least one of --chatgpt or --instagram")


async def main() -> None:
    ctx = ContextUse.from_config(
        {
            "storage": {"provider": "disk", "config": {"base_path": "./data"}},
            "db": {
                "provider": "postgres",
                "config": {
                    "host": "localhost",
                    "port": 5432,
                    "database": "context_use",
                    "user": "postgres",
                    "password": "postgres",
                },
            },
        }
    )
    await ctx.init_db()

    if args.chatgpt:
        print(f"Processing ChatGPT archive: {args.chatgpt}")
        result = await ctx.process_archive(Provider.CHATGPT, args.chatgpt)
        print(
            f"  ChatGPT: {result.threads_created} threads from "
            f"{result.tasks_completed} tasks"
        )
        if result.errors:
            print(f"  Errors: {result.errors}")

    if args.instagram:
        print(f"\nProcessing Instagram archive: {args.instagram}")
        result = await ctx.process_archive(Provider.INSTAGRAM, args.instagram)
        print(
            f"  Instagram: {result.threads_created} threads from "
            f"{result.tasks_completed} tasks"
        )
        if result.errors:
            print(f"  Errors: {result.errors}")

    print("\nDone! Data stored in ./context_use.db and ./data/")


asyncio.run(main())

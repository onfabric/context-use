from __future__ import annotations

import argparse
import asyncio
from importlib.metadata import version

from context_use.cli.commands import COMMAND_GROUPS, TOP_LEVEL_COMMANDS

DESCRIPTION = """\
context-use — turn your data exports into portable AI memory

Turn data exports from ChatGPT, Instagram, and other platforms into personal memories.
Port your memories to your favorite AI agents so they can understand you more like a
friend and less like a chatbot.

Quick start: context-use pipeline --quick"""

_EPILOG = (
    "Quick start (real-time API, last 30 days):\n"
    "  context-use pipeline --quick                 "
    "Ingest + memories preview\n"
    "\n"
    "Full pipeline (batch API):\n"
    "  context-use pipeline                         "
    "Ingest + memories in one go\n"
    "\n"
    "Or step by step:\n"
    "  1. context-use ingest                        "
    "Parse an archive\n"
    "  2. context-use memories generate             "
    "Generate memories (batch API)\n"
    "\n"
    "Explore:\n"
    "  context-use memories list                    "
    "Browse memories\n"
    '  context-use memories search "query"          '
    "Semantic search\n"
    "  context-use memories export                  "
    "Export to file\n"
    "\n"
    "Personal agent:\n"
    "  context-use agent synthesise                 "
    "Synthesise pattern memories\n"
    '  context-use agent ask "prompt"                '
    "Send a free-form task to the agent\n"
    "\n"
    "Configuration:\n"
    "  context-use config show                      "
    "Show current settings\n"
    "  context-use config set-key                   "
    "Change OpenAI API key\n"
    "  context-use config path                      "
    "Print config file location\n"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-use",
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_EPILOG,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version('context-use')}",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed progress logs (polling, state transitions)",
    )
    sub = parser.add_subparsers(dest="command", title="commands")

    for cmd_class in TOP_LEVEL_COMMANDS:
        cmd_class().register(sub)

    for group_class in COMMAND_GROUPS:
        group_class().register(sub)

    return parser


def main() -> None:
    import logging

    parser = _build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="  %(name)s: %(message)s")
    logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
    logging.getLogger("litellm").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if not hasattr(args, "func") or args.func is None:
        parser.print_help()
        return

    try:
        asyncio.run(args.func(args))
    except KeyboardInterrupt:
        print()

from __future__ import annotations

import argparse
import asyncio
from importlib.metadata import version

from context_use.cli.commands import COMMAND_GROUPS, TOP_LEVEL_COMMANDS

_BANNER_ART = (
    "                ▐▌             ▐▌                      \n"
    " ▟██▖ ▟█▙ ▐▙██▖▐███  ▟█▙ ▝█ █▘▐███      ▐▌ ▐▌▗▟██▖ ▟█▙ \n"
    "▐▛  ▘▐▛ ▜▌▐▛ ▐▌ ▐▌  ▐▙▄▟▌ ▐█▌  ▐▌       ▐▌ ▐▌▐▙▄▖▘▐▙▄▟▌\n"
    "▐▌   ▐▌ ▐▌▐▌ ▐▌ ▐▌  ▐▛▀▀▘ ▗█▖  ▐▌   ██▌ ▐▌ ▐▌ ▀▀█▖▐▛▀▀▘\n"
    "▝█▄▄▌▝█▄█▘▐▌ ▐▌ ▐▙▄ ▝█▄▄▌ ▟▀▙  ▐▙▄      ▐▙▄█▌▐▄▄▟▌▝█▄▄▌\n"
    " ▝▀▀  ▝▀▘ ▝▘ ▝▘  ▀▀  ▝▀▀ ▝▀ ▀▘  ▀▀       ▀▀▝▘ ▀▀▀  ▝▀▀ "
)


_HEADLINE = "Portable AI memory from your conversations and data exports"

_EPILOG = (
    "examples:\n"
    "  context-use proxy                            Start the memory proxy\n"
    '  context-use memories search "cooking"        Search your memories\n'
    '  context-use agent ask "summarise March"      Ask the personal agent\n'
    "  context-use pipeline --quick export.zip      Import a data export\n"
    "  context-use pipeline                         Full pipeline (batch API)\n"
)


def _banner() -> str:
    try:
        ver = version("context-use")
        return f"\n{_BANNER_ART}  v{ver}\n\n{_HEADLINE}\n"
    except UnicodeEncodeError:
        return ""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-use",
        description=_banner(),
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

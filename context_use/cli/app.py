from __future__ import annotations

import argparse
import asyncio
from importlib.metadata import version

from context_use.cli.commands import COMMAND_GROUPS, TOP_LEVEL_COMMANDS

_BANNER_ART = (
    "                     __                   __                                      \n"  # noqa: E501
    "                    /\\ \\__               /\\ \\__                                   \n"  # noqa: E501
    "  ___    ___     ___\\ \\ ,_\\    __   __  _\\ \\ ,_\\          __  __    ____     __   \n"  # noqa: E501
    " /'___\\ / __`\\ /' _ `\\ \\ \\/  /'__`\\/\\ \\/'\\\\ \\ \\/  _______/\\ \\/\\ \\  /',__\\  /'__`\\ \n"  # noqa: E501
    "/\\ \\__//\\ \\L\\ \\/\\ \\/\\ \\ \\ \\_/\\  __/\\/>  </ \\ \\ \\_/\\______\\ \\ \\_\\ \\/\\__, `\\/\\  __/ \n"  # noqa: E501
    "\\ \\____\\ \\____/\\ \\_\\ \\_\\ \\__\\ \\____\\/\\_/\\_\\ \\ \\__\\/______/\\ \\____/\\/\\____/\\ \\____\\\n"  # noqa: E501
    " \\/____/\\/___/  \\/_/\\/_/\\/__/\\/____/\\//\\/_/  \\/__/         \\/___/  \\/___/  \\/____/"  # noqa: E501
)


_HEADLINE = "Turn your data exports into portable AI memory"

DESCRIPTION = """\

Quick start: context-use pipeline --quick <zip-path>"""

_EPILOG = (
    "Quick start (real-time API, last 30 days):\n"
    "  context-use pipeline --quick <zip-path>      "
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
    '  context-use memories search "<your-query>"   '
    "Semantic search\n"
    "  context-use memories export                  "
    "Export to file\n"
    "\n"
    "Personal agent:\n"
    "  context-use agent synthesise                 "
    "Synthesise pattern memories\n"
    '  context-use agent ask "<your-prompt>"        '
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


def _print_banner() -> None:
    try:
        ver = version("context-use")
        print(f"{_BANNER_ART}  v{ver}")
        print()
        print(f"{_HEADLINE}\n")
    except UnicodeEncodeError:
        pass


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
        _print_banner()
        parser.print_help()
        return

    try:
        asyncio.run(args.func(args))
    except KeyboardInterrupt:
        print()

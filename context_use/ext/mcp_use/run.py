#!/usr/bin/env python
# pyright: reportMissingImports=false
"""Standalone MCP server entry point for context-use.

Usage::

    python -m context_use.ext.mcp_use.run
    python -m context_use.ext.mcp_use.run --transport stdio
    python -m context_use.ext.mcp_use.run --host 127.0.0.1 --port 3000

Reads the same TOML config as the ``context-use`` CLI.
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m context_use.ext.mcp_use.run",
        description="Start the context-use MCP server.",
    )
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "stdio"],
        default="streamable-http",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    from context_use.cli.app import _build_ctx
    from context_use.cli.config import load_config

    cfg = load_config()
    if cfg.store_provider != "postgres":
        sys.exit(
            "error: MCP server requires PostgreSQL.\n"
            "  Run: context-use config set-store postgres"
        )

    from context_use.ext.mcp_use.server import create_server

    server = create_server(_build_ctx(cfg))

    kwargs: dict = {"transport": args.transport}
    if args.transport == "streamable-http":
        kwargs.update(host=args.host, port=args.port)
    server.run(**kwargs)


if __name__ == "__main__":
    main()

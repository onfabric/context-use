"""Test MCP server — thin CLI runner over context_use.ext.mcp_use.

Usage:
    uv run tests/mcp_server.py                         # streamable-http on :8000
    uv run tests/mcp_server.py --transport stdio        # stdio for MCP clients
    uv run tests/mcp_server.py --port 9000 --debug      # custom port + inspector UI
"""

from __future__ import annotations

import argparse
import os

from context_use.db.postgres import PostgresBackend
from context_use.ext.mcp_use.server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(description="context-use MCP server")
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "stdio"],
        default="streamable-http",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    db = PostgresBackend(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB", "context_use"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
    )

    server = create_server(
        db=db,
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
    )

    kwargs: dict = {"transport": args.transport}
    if args.transport == "streamable-http":
        kwargs.update(host=args.host, port=args.port)
    if args.debug:
        kwargs["debug"] = True

    server.run(**kwargs)


if __name__ == "__main__":
    main()

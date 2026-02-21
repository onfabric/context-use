"""Test MCP server — thin CLI runner over context_use.ext.mcp_use.

Usage:
    uv run tests/ext/mcp_server.py                     # streamable-http on :8000
    uv run tests/ext/mcp_server.py --transport stdio    # stdio for MCP clients
    uv run tests/ext/mcp_server.py --port 9000          # custom port
"""

from __future__ import annotations

import argparse
import os

from context_use import ContextUse
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
    args = parser.parse_args()

    ctx = ContextUse.from_config(
        {
            "storage": {
                "provider": "disk",
                "config": {"base_path": "./data/storage"},
            },
            "db": {
                "provider": "postgres",
                "config": {
                    "host": os.environ.get("POSTGRES_HOST", "localhost"),
                    "port": int(os.environ.get("POSTGRES_PORT", "5432")),
                    "database": os.environ.get("POSTGRES_DB", "context_use"),
                    "user": os.environ.get("POSTGRES_USER", "postgres"),
                    "password": os.environ.get("POSTGRES_PASSWORD", "postgres"),
                },
            },
            "llm": {"api_key": os.environ.get("OPENAI_API_KEY", "")},
        }
    )

    server = create_server(ctx)

    kwargs: dict = {"transport": args.transport}
    if args.transport == "streamable-http":
        kwargs.update(host=args.host, port=args.port)

    server.run(**kwargs)


if __name__ == "__main__":
    main()

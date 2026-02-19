"""Interactive agent that answers questions using the context-use MCP server.

Start the MCP server first:
    uv run tests/mcp_server.py

Then in another terminal:
    uv run tests/agent.py "What did I do in Rome?"
    uv run tests/agent.py --interactive
"""

from __future__ import annotations

import argparse
import asyncio
import os

from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient
from pydantic import SecretStr

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8000/mcp")


async def run_query(query: str) -> str:
    client = MCPClient.from_dict(
        {
            "mcpServers": {
                "context-use": {
                    "url": MCP_SERVER_URL,
                },
            },
        }
    )

    api_key = os.environ.get("OPENAI_API_KEY")
    llm = ChatOpenAI(
        model="gpt-4o",
        api_key=SecretStr(api_key) if api_key else None,
    )

    agent = MCPAgent(llm=llm, client=client, max_steps=30)

    try:
        result = await agent.run(query)
        return result
    finally:
        await client.close_all_sessions()


async def interactive() -> None:
    print("Memory agent (type 'quit' to exit)\n")
    while True:
        try:
            query = input("> ").strip()
        except EOFError, KeyboardInterrupt:
            break
        if not query or query.lower() in ("quit", "exit", "q"):
            break
        result = await run_query(query)
        print(f"\n{result}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent that answers questions via the context-use MCP server"
    )
    parser.add_argument("query", nargs="?", help="One-shot question")
    parser.add_argument(
        "--interactive", action="store_true", help="Interactive REPL mode"
    )
    args = parser.parse_args()

    if args.interactive:
        asyncio.run(interactive())
    elif args.query:
        result = asyncio.run(run_query(args.query))
        print(result)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

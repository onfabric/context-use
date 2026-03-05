from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from context_use.cli import output as out
from context_use.cli.base import PersistentApiCommand
from context_use.config import Config

if TYPE_CHECKING:
    from context_use import ContextUse


async def _rag_answer(ctx: ContextUse, query: str, *, top_k: int = 10) -> str:
    """Return an answer grounded in the user's stored memories."""
    results = await ctx.search_memories(query=query, top_k=top_k)

    parts: list[str] = [
        "You are a helpful assistant with access to the user's personal "
        "memories. Answer their question based on the context "
        "below. Be specific and reference dates/details from the memories. "
        "If the context doesn't contain enough information, say so honestly."
    ]

    if results:
        parts.append("\n## Relevant Memories\n")
        for r in results:
            parts.append(f"- [{r.from_date}] {r.content}")

    parts.append(f"\n## Question\n\n{query}")

    return await ctx._llm_client.completion("\n".join(parts))


class AskCommand(PersistentApiCommand):
    name = "ask"
    help = "Ask a question about your memories (requires PostgreSQL)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("query", nargs="?", help="Your question")
        parser.add_argument(
            "--interactive", action="store_true", help="Interactive chat mode"
        )

    async def run(
        self,
        cfg: Config,
        ctx: ContextUse,
        args: argparse.Namespace,
    ) -> None:
        interactive = args.interactive or args.query is None

        if interactive:
            print()
            out.banner()
            out.info("Ask questions about your memories. Type 'quit' to exit.\n")

        while True:
            if interactive:
                try:
                    query = input(out.cyan("> ")).strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not query or query.lower() in ("quit", "exit", "q"):
                    break
            else:
                query = args.query

            answer = await _rag_answer(ctx, query)
            print(f"\n{answer}\n")

            if not interactive:
                break

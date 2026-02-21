"""Semantic search over stored memories using the core search module.

Usage:
    uv run tests/search_memories.py "what did I do last summer?"
    uv run tests/search_memories.py "coffee with friends" --top-k 10
"""

from __future__ import annotations

import argparse
import asyncio
import os

from context_use.db.postgres import PostgresBackend
from context_use.llm.base import LLMClient
from context_use.llm.models import OpenAIEmbeddingModel, OpenAIModel
from context_use.search.memories import search_memories


async def search(query: str, top_k: int = 5) -> None:
    db = PostgresBackend(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB", "context_use"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
    )
    llm_client = LLMClient(
        model=OpenAIModel.GPT_4O,
        api_key=os.environ["OPENAI_API_KEY"],
        embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
    )

    print(f"Embedding query: {query!r}")
    async with db.session_scope() as session:
        results = await search_memories(
            session,
            query=query,
            top_k=top_k,
            llm_client=llm,
        )

    if not results:
        print("No embedded memories found in the database.")
        return

    print(f"\nTop {len(results)} results:\n")
    for i, r in enumerate(results, 1):
        sim = f" (similarity={r.similarity:.4f})" if r.similarity is not None else ""
        print(f"  {i}. [{r.from_date}]{sim}")
        print(f"     {r.content}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic search over memories")
    parser.add_argument("query", help="Natural-language search query")
    parser.add_argument(
        "--top-k", type=int, default=5, help="Number of results (default: 5)"
    )
    args = parser.parse_args()

    asyncio.run(search(args.query, top_k=args.top_k))


if __name__ == "__main__":
    main()

"""E2E: test refinement pipeline against existing memories in DB.

Runs discovery to find clusters of similar memories, then optionally
submits them for LLM refinement.

Usage:
    # Discovery only (dry run):
    uv run tests/e2e_refinement.py

    # Full refinement (discovery + LLM merge + embed):
    uv run tests/e2e_refinement.py --run

    # Tweak discovery params:
    uv run tests/e2e_refinement.py --similarity 0.3 --days 14
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime

import context_use.memories.refinement.manager  # noqa: F401
from context_use.batch.runner import run_pipeline
from context_use.llm import LLMClient, OpenAIEmbeddingModel, OpenAIModel
from context_use.memories.refinement.discovery import discover_refinement_clusters
from context_use.memories.refinement.factory import RefinementBatchFactory
from context_use.models.memory import MemoryStatus
from context_use.store.postgres import PostgresStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_store() -> PostgresStore:
    return PostgresStore(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB", "context_use"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
    )


async def run_discovery(
    store: PostgresStore,
    *,
    similarity_threshold: float,
    date_proximity_days: int,
    max_candidates: int,
) -> list[list[str]]:
    """Run discovery against all active, embedded memories."""
    all_ids = await store.get_refinable_memory_ids()
    print(f"\n{len(all_ids)} active embedded memories in DB")

    if not all_ids:
        print("Nothing to refine.")
        return []

    clusters = await discover_refinement_clusters(
        seed_memory_ids=all_ids,
        store=store,
        similarity_threshold=similarity_threshold,
        date_proximity_days=date_proximity_days,
        max_candidates_per_seed=max_candidates,
    )
    return clusters


async def print_clusters(store: PostgresStore, clusters: list[list[str]]) -> None:
    """Pretty-print discovered clusters with memory content."""
    for i, cluster_ids in enumerate(clusters):
        memories = await store.get_memories(cluster_ids)
        memories.sort(key=lambda m: m.from_date)

        print(f"\n--- Cluster {i + 1} ({len(memories)} memories) ---")
        for m in memories:
            content = m.content[:120] + "..." if len(m.content) > 120 else m.content
            print(f"  [{m.from_date} -> {m.to_date}] {content}")


async def run_full_refinement(store: PostgresStore) -> None:
    """Create a refinement batch and run it through the pipeline."""
    llm_client = LLMClient(
        model=OpenAIModel.GPT_4O,
        api_key=os.environ["OPENAI_API_KEY"],
        embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
    )

    batches = await RefinementBatchFactory.create_refinement_batches(store=store)

    if not batches:
        print("No refinement batches created.")
        return

    print(f"\nCreated {len(batches)} refinement batch(es)")
    print("Running refinement pipeline...")

    await run_pipeline(
        batches,
        store=store,
        manager_kwargs={"llm_client": llm_client},
    )

    for batch in batches:
        print(f"\nBatch {batch.id} final status: {batch.current_status}")

    # Report results
    all_memories = await store.list_memories(status=MemoryStatus.active.value)
    refined = [m for m in all_memories if m.source_memory_ids]
    superseded = await store.list_memories(status=MemoryStatus.superseded.value)

    print("\n=== Refinement Results ===")
    print(f"Refined memories created: {len(refined)}")
    print(f"Memories superseded: {len(superseded)}")

    report_entries = []
    for m in refined:
        print(
            f"\n  [{m.from_date} -> {m.to_date}]"
            f"\n  {m.content}"
            f"\n  Sources: {m.source_memory_ids}"
        )

        source_memories = []
        if m.source_memory_ids:
            sources = await store.get_memories(m.source_memory_ids)
            for src in sources:
                source_memories.append(
                    {
                        "id": src.id,
                        "content": src.content,
                        "from_date": src.from_date.isoformat(),
                        "to_date": src.to_date.isoformat(),
                        "status": src.status,
                    }
                )
            source_memories.sort(key=lambda s: s["from_date"])

        report_entries.append(
            {
                "refined_memory": {
                    "id": m.id,
                    "content": m.content,
                    "from_date": m.from_date.isoformat(),
                    "to_date": m.to_date.isoformat(),
                    "source_memory_ids": m.source_memory_ids,
                },
                "source_memories": source_memories,
            }
        )

    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "refined_count": len(refined),
            "superseded_count": len(superseded),
        },
        "results": report_entries,
    }

    report_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "data",
        "memories",
        f"refinement_report_{datetime.now().strftime('%Y%m%dT%H%M%SZ')}.json",
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport written to {os.path.abspath(report_path)}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="E2E refinement test")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Actually run refinement (not just discovery)",
    )
    parser.add_argument(
        "--similarity",
        type=float,
        default=0.4,
        help="Cosine similarity threshold (default: 0.4)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Date proximity in days (default: 7)",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=10,
        help="Max candidates per seed (default: 10)",
    )
    args = parser.parse_args()

    store = get_store()
    await store.init()

    print("=== Discovery ===")
    clusters = await run_discovery(
        store,
        similarity_threshold=args.similarity,
        date_proximity_days=args.days,
        max_candidates=args.max_candidates,
    )

    if not clusters:
        print("\nNo clusters found. Try lowering --similarity or increasing --days.")
        await store.close()
        return

    print(f"\nFound {len(clusters)} clusters")
    await print_clusters(store, clusters)

    if args.run:
        print("\n=== Running Refinement ===")
        await run_full_refinement(store)
    else:
        total_memories = sum(len(c) for c in clusters)
        print(
            f"\nDry run complete. {len(clusters)} clusters, "
            f"{total_memories} total memories."
        )
        print("Re-run with --run to submit to the LLM.")

    await store.close()


if __name__ == "__main__":
    asyncio.run(main())

"""E2E: test refinement pipeline against existing memories in DB.

Runs discovery to find clusters of similar memories, then optionally
submits them for LLM refinement.

Usage:
    # Discovery only (dry run) — see what clusters would be formed:
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

from sqlalchemy import func, select

import context_use.memories.refinement.manager  # noqa: F401
from context_use.batch.models import Batch, BatchCategory
from context_use.batch.runner import run_pipeline
from context_use.batch.states import CreatedState
from context_use.db.postgres import PostgresBackend
from context_use.llm import LLMClient, OpenAIEmbeddingModel, OpenAIModel
from context_use.memories.models import MemoryStatus, TapestryMemory
from context_use.memories.refinement.discovery import discover_refinement_clusters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db() -> PostgresBackend:
    return PostgresBackend(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB", "context_use"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
    )


async def run_discovery(
    db: PostgresBackend,
    *,
    similarity_threshold: float,
    date_proximity_days: int,
    max_candidates: int,
) -> list[list[str]]:
    """Run discovery against all active, embedded memories."""
    session = db.get_session()
    try:
        result = await session.execute(
            select(TapestryMemory.id).where(
                TapestryMemory.status == MemoryStatus.active.value,
                TapestryMemory.embedding.isnot(None),
            )
        )
        all_ids = [row[0] for row in result.all()]
        print(f"\n{len(all_ids)} active embedded memories in DB")

        if not all_ids:
            print("Nothing to refine.")
            return []

        clusters = await discover_refinement_clusters(
            seed_memory_ids=all_ids,
            db=session,
            similarity_threshold=similarity_threshold,
            date_proximity_days=date_proximity_days,
            max_candidates_per_seed=max_candidates,
        )
        return clusters
    finally:
        await session.close()


async def print_clusters(db: PostgresBackend, clusters: list[list[str]]) -> None:
    """Pretty-print discovered clusters with memory content."""
    session = db.get_session()
    try:
        for i, cluster_ids in enumerate(clusters):
            result = await session.execute(
                select(TapestryMemory).where(TapestryMemory.id.in_(cluster_ids))
            )
            memories = list(result.scalars().all())
            memories.sort(key=lambda m: m.from_date)

            print(f"\n--- Cluster {i + 1} ({len(memories)} memories) ---")
            for m in memories:
                print(
                    f"  [{m.from_date} → {m.to_date}] {m.content[:120]}..."
                    if len(m.content) > 120
                    else f"  [{m.from_date} → {m.to_date}] {m.content}"
                )
    finally:
        await session.close()


async def run_full_refinement(
    db: PostgresBackend,
    clusters: list[list[str]],
) -> None:
    """Create a refinement batch and run it through the pipeline."""
    llm_client = LLMClient(
        model=OpenAIModel.GPT_4O,
        api_key=os.environ["OPENAI_API_KEY"],
        embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
    )

    # Phase 1: create the batch in its own session.
    async with db.session_scope() as session:
        seed_ids = list({mid for cluster in clusters for mid in cluster})

        from context_use.etl.models.etl_task import EtlTask

        etl_result = await session.execute(select(EtlTask.id).limit(1))
        etl_task_row = etl_result.first()
        if not etl_task_row:
            print("No ETL task found — cannot create refinement batch")
            return
        etl_task_id = etl_task_row[0]

        initial_state = CreatedState()
        state_dict = initial_state.model_dump(mode="json")
        state_dict["seed_memory_ids"] = seed_ids

        batch = Batch(
            etl_task_id=etl_task_id,
            batch_number=1,
            category=BatchCategory.refinement.value,
            states=[state_dict],
        )
        session.add(batch)

    print(f"\nCreated refinement batch {batch.id} with {len(seed_ids)} seeds")
    print("Running refinement pipeline...")

    # Phase 2: run pipeline — manager creates its own sessions.
    await run_pipeline(
        [batch],
        db_backend=db,
        manager_kwargs={"llm_client": llm_client},
    )

    print(f"\nBatch final status: {batch.current_status}")

    # Report results
    session = db.get_session()
    try:
        result = await session.execute(
            select(TapestryMemory).where(
                TapestryMemory.source_memory_ids.isnot(None),
                TapestryMemory.status == MemoryStatus.active.value,
            )
        )
        refined = list(result.scalars().all())

        superseded_count = (
            await session.execute(
                select(func.count()).where(
                    TapestryMemory.status == MemoryStatus.superseded.value,
                )
            )
        ).scalar()

        print("\n=== Refinement Results ===")
        print(f"Refined memories created: {len(refined)}")
        print(f"Memories superseded: {superseded_count}")

        report_entries = []
        for m in refined:
            print(
                f"\n  [{m.from_date} → {m.to_date}]"
                f"\n  {m.content}"
                f"\n  Sources: {m.source_memory_ids}"
            )

            superseded_memories = []
            if m.source_memory_ids:
                result = await session.execute(
                    select(TapestryMemory).where(
                        TapestryMemory.id.in_(m.source_memory_ids)
                    )
                )
                for src in result.scalars().all():
                    superseded_memories.append(
                        {
                            "id": src.id,
                            "content": src.content,
                            "from_date": src.from_date.isoformat(),
                            "to_date": src.to_date.isoformat(),
                            "status": src.status,
                        }
                    )
                superseded_memories.sort(key=lambda s: s["from_date"])

            report_entries.append(
                {
                    "refined_memory": {
                        "id": m.id,
                        "content": m.content,
                        "from_date": m.from_date.isoformat(),
                        "to_date": m.to_date.isoformat(),
                        "source_memory_ids": m.source_memory_ids,
                    },
                    "superseded_memories": superseded_memories,
                }
            )

        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "refined_count": len(refined),
                "superseded_count": superseded_count,
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

    finally:
        await session.close()


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

    db = get_db()

    print("=== Discovery ===")
    clusters = await run_discovery(
        db,
        similarity_threshold=args.similarity,
        date_proximity_days=args.days,
        max_candidates=args.max_candidates,
    )

    if not clusters:
        print("\nNo clusters found. Try lowering --similarity or increasing --days.")
        return

    print(f"\nFound {len(clusters)} clusters")
    await print_clusters(db, clusters)

    if args.run:
        print("\n=== Running Refinement ===")
        await run_full_refinement(db, clusters)
    else:
        total_memories = sum(len(c) for c in clusters)
        print(
            f"\nDry run complete. {len(clusters)} clusters, "
            f"{total_memories} total memories."
        )
        print("Re-run with --run to submit to the LLM.")


if __name__ == "__main__":
    asyncio.run(main())

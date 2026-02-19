"""E2E: Instagram zip → ETL → batch creation → memory generation → embedding → DB.

Usage:
    uv run tests/e2e_memories_pipeline.py --instagram data/your-instagram-export.zip
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from sqlalchemy import select

from context_use import ContextUse
from context_use.batch.runner import run_batches
from context_use.db.postgres import PostgresBackend
from context_use.etl.models.base import Base
from context_use.etl.models.etl_task import EtlTask
from context_use.etl.providers.registry import Provider
from context_use.llm import LLMClient, OpenAIEmbeddingModel, OpenAIModel
from context_use.memories.factory import MemoryBatchFactory
from context_use.memories.manager import (
    MemoryBatchManager,  # noqa: F401 (registers via decorator)
)
from context_use.memories.models import TapestryMemory
from context_use.storage.disk import DiskStorage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STORAGE_BASE_PATH = "./data"


async def clean_db(db: PostgresBackend) -> None:
    async with db.session_scope() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
    logger.info("Cleaned all tables")


async def main() -> None:
    parser = argparse.ArgumentParser(description="E2E memories pipeline")
    parser.add_argument(
        "--instagram", required=True, metavar="PATH", help="Path to Instagram zip"
    )
    parser.add_argument(
        "--yolo", action="store_true", help="Use GPT-5.2 instead of GPT-4o"
    )
    args = parser.parse_args()

    storage = DiskStorage(base_path=STORAGE_BASE_PATH)
    db = PostgresBackend(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB", "context_use"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
    )

    ctx = ContextUse(storage=storage, db=db)

    # ---- Step 0: clean slate ----
    print("\n=== Step 0: Cleaning DB ===")
    await clean_db(db)

    # ---- Step 1: ETL ----
    print("\n=== Step 1: ETL ===")
    result = await ctx.process_archive(Provider.INSTAGRAM, args.instagram)
    print(
        f"Archive {result.archive_id}: "
        f"{result.threads_created} threads, "
        f"{result.tasks_completed} task(s) completed"
    )
    if result.errors:
        print(f"  Errors: {result.errors}")

    # ---- Step 2: create batches ----
    print("\n=== Step 2: Create batches ===")
    session = db.get_session()

    stmt = select(EtlTask).where(EtlTask.archive_id == result.archive_id)

    tasks = await session.execute(stmt)
    tasks = tasks.scalars().all()
    print(f"Found {len(tasks)} ETL task(s)")

    all_batches = []
    for task in tasks:
        batches = await MemoryBatchFactory.create_batches(
            etl_task_id=task.id,
            db=session,
        )
        all_batches.extend(batches)

    print(f"Created {len(all_batches)} batch(es)")

    if not all_batches:
        print("No batches to process — exiting.")
        await session.close()
        return

    # ---- Step 3: run memory pipeline ----
    print("\n=== Step 3: Run memory pipeline ===")
    model = OpenAIModel.GPT_5_2 if args.yolo else OpenAIModel.GPT_4O
    print(f"Using model: {model}")
    llm_client = LLMClient(
        model=model,
        api_key=os.environ["OPENAI_API_KEY"],
        embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
    )

    await run_batches(
        all_batches,
        db=session,
        manager_kwargs={
            "llm_client": llm_client,
            "storage": storage,
        },
    )

    # ---- Step 4: report ----
    print("\n=== Results ===")
    session.expire_all()
    stmt = select(TapestryMemory)
    memories = await session.execute(stmt)
    memories = memories.scalars().all()
    print(f"{len(memories)} memories in DB:")
    for m in memories:
        has_emb = m.embedding is not None
        print(f"  [{m.from_date}] {m.content[:100]}  (embedded={has_emb})")

    await session.close()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())

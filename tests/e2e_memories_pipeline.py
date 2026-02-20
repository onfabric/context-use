"""E2E: archive zip → ETL → batch creation → memory generation → embedding → DB.

Usage:
    uv run tests/e2e_memories_pipeline.py --instagram data/your-instagram-export.zip
    uv run tests/e2e_memories_pipeline.py --chatgpt data/your-chatgpt-export.zip
    uv run tests/e2e_memories_pipeline.py --instagram ig.zip --chatgpt chatgpt.zip
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

import context_use.memories.providers  # noqa: F401 (registers memory configs)
from context_use import ContextUse
from context_use.batch.runner import run_pipeline
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
from context_use.memories.registry import get_memory_config
from context_use.storage.disk import DiskStorage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STORAGE_BASE_PATH = "./data"


async def clean_db(db: PostgresBackend) -> None:
    async with db.get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Dropped and recreated all tables")


async def main() -> None:
    parser = argparse.ArgumentParser(description="E2E memories pipeline")
    parser.add_argument("--instagram", metavar="PATH", help="Path to Instagram zip")
    parser.add_argument("--chatgpt", metavar="PATH", help="Path to ChatGPT zip")
    parser.add_argument(
        "--yolo", action="store_true", help="Use GPT-5.2 instead of GPT-4o"
    )
    parser.add_argument(
        "--window-days", type=int, default=5, help="Window size in days (default: 5)"
    )
    parser.add_argument(
        "--overlap-days",
        type=int,
        default=1,
        help="Overlap between windows (default: 1)",
    )
    args = parser.parse_args()

    archives: list[tuple[Provider, str]] = []
    if args.instagram:
        archives.append((Provider.INSTAGRAM, args.instagram))
    if args.chatgpt:
        archives.append((Provider.CHATGPT, args.chatgpt))

    if not archives:
        parser.error("At least one of --instagram or --chatgpt is required")

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
    print("\n=== Step 0: Initializing & cleaning DB ===")
    await db.init_db()
    await clean_db(db)

    # ---- Step 1: ETL ----
    print("\n=== Step 1: ETL ===")
    all_archive_ids: list[str] = []
    for provider, path in archives:
        result = await ctx.process_archive(provider, path)
        all_archive_ids.append(result.archive_id)
        print(
            f"[{provider.value}] Archive {result.archive_id}: "
            f"{result.threads_created} threads, "
            f"{result.tasks_completed} task(s) completed"
        )
        if result.errors:
            print(f"  Errors: {result.errors}")

    # ---- Step 2: create batches ----
    print("\n=== Step 2: Create batches ===")
    session = db.get_session()

    stmt = select(EtlTask).where(EtlTask.archive_id.in_(all_archive_ids))
    tasks = (await session.execute(stmt)).scalars().all()
    print(f"Found {len(tasks)} ETL task(s)")

    all_batches = []
    for task in tasks:
        config = get_memory_config(task.interaction_type)
        grouper = config.create_grouper()
        batches = await MemoryBatchFactory.create_batches(
            etl_task_id=task.id,
            db=session,
            grouper=grouper,
        )
        all_batches.extend(batches)
        print(
            f"  [{task.interaction_type}] {len(batches)} batch(es) "
            f"(grouper: {type(grouper).__name__})"
        )

    print(f"Created {len(all_batches)} batch(es) total")

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

    await run_pipeline(
        all_batches,
        db=session,
        manager_kwargs={
            "llm_client": llm_client,
            "storage": storage,
        },
    )

    # ---- Step 4: report & dump ----
    print("\n=== Results ===")
    session.expire_all()
    result = await session.execute(
        select(TapestryMemory).order_by(
            TapestryMemory.from_date, TapestryMemory.to_date
        )
    )
    memories = result.scalars().all()
    print(f"{len(memories)} memories in DB:")
    for m in memories:
        print(f"  [{m.from_date}] {m.content[:100]}")

    rows = [
        {
            "content": m.content,
            "from_date": m.from_date.isoformat(),
            "to_date": m.to_date.isoformat(),
        }
        for m in memories
    ]
    out_dir = Path("data/memories")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"memories_{ts}.json"
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"\nWrote {len(rows)} memories to {out_path}")

    await session.close()


if __name__ == "__main__":
    asyncio.run(main())

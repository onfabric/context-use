"""E2E: archive zip -> ETL -> batch creation -> memory generation -> embedding -> DB.

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

from context_use import ContextUse
from context_use.llm import LLMClient, OpenAIEmbeddingModel, OpenAIModel
from context_use.models.memory import MemoryStatus
from context_use.providers.registry import Provider
from context_use.storage.disk import DiskStorage
from context_use.store.postgres import PostgresStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STORAGE_BASE_PATH = "./data"


async def main() -> None:
    parser = argparse.ArgumentParser(description="E2E memories pipeline")
    parser.add_argument("--instagram", metavar="PATH", help="Path to Instagram zip")
    parser.add_argument("--chatgpt", metavar="PATH", help="Path to ChatGPT zip")
    parser.add_argument(
        "--yolo", action="store_true", help="Use GPT-5.2 instead of GPT-4o"
    )
    args = parser.parse_args()

    archives: list[tuple[Provider, str]] = []
    if args.instagram:
        archives.append((Provider.INSTAGRAM, args.instagram))
    if args.chatgpt:
        archives.append((Provider.CHATGPT, args.chatgpt))

    if not archives:
        parser.error("At least one of --instagram or --chatgpt is required")

    model = OpenAIModel.GPT_5_2 if args.yolo else OpenAIModel.GPT_4O
    print(f"Using model: {model}")
    llm_client = LLMClient(
        model=model,
        api_key=os.environ["OPENAI_API_KEY"],
        embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
    )

    storage = DiskStorage(base_path=STORAGE_BASE_PATH)
    store = PostgresStore(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB", "context_use"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
    )

    ctx = ContextUse(storage=storage, store=store, llm_client=llm_client)

    # ---- Step 0: clean slate ----
    print("\n=== Step 0: Initializing & cleaning DB ===")
    await store.reset()

    # ---- Step 1: ETL ----
    print("\n=== Step 1: ETL ===")
    archive_ids: list[str] = []
    for provider, path in archives:
        result = await ctx.process_archive(provider, path)
        archive_ids.append(result.archive_id)
        print(
            f"[{provider.value}] Archive {result.archive_id}: "
            f"{result.threads_created} threads, "
            f"{result.tasks_completed} task(s) completed"
        )
        if result.errors:
            print(f"  Errors: {result.errors}")

    # ---- Step 2: generate memories ----
    print("\n=== Step 2: Generate memories ===")

    mem_result = await ctx.generate_memories(archive_ids)
    print(
        f"Processed {mem_result.tasks_processed} task(s), "
        f"created {mem_result.batches_created} batch(es)"
    )
    if mem_result.errors:
        print(f"  Errors: {mem_result.errors}")

    # ---- Step 3: report & dump ----
    print("\n=== Results ===")
    memories = await store.list_memories(status=MemoryStatus.active.value)
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


if __name__ == "__main__":
    asyncio.run(main())

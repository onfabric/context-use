"""Smoke-test: Instagram data → memory generation (batch) → embedding (batch)."""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from context_use.etl.models.thread import Thread
from context_use.llm import EmbedItem, LLMClient, OpenAIEmbeddingModel, OpenAIModel
from context_use.memories.prompt import MemoryPromptBuilder, MemorySchema

logging.basicConfig(level=logging.INFO)

DATA_ROOT = Path("data/616493c0-d385-42bc-96ce-ea2a7b90c49d")
STORIES_JSON = DATA_ROOT / "your_instagram_activity/media/stories.json"

MAX_THREADS = 10
POLL_INTERVAL_SECS = 30
POLL_MAX_ATTEMPTS = 60


class FakeThread:
    """Duck-typed Thread for smoke testing without a database."""

    def __init__(self, id: str, preview: str, asset_uri: str, asat: datetime):
        self.id = id
        self.preview = preview
        self.asset_uri = asset_uri
        self.asat = asat


def load_threads_from_instagram(limit: int = MAX_THREADS) -> list[FakeThread]:
    with open(STORIES_JSON) as f:
        data = json.load(f)

    threads = []
    for story in data.get("ig_stories", [])[:limit]:
        uri = story["uri"]
        asset_path = str(DATA_ROOT / uri)

        if not Path(asset_path).exists():
            continue

        asat = datetime.fromtimestamp(story["creation_timestamp"], tz=UTC)
        preview = story.get("title") or f"Instagram story from {asat.date()}"

        threads.append(
            FakeThread(
                id=uri.split("/")[-1].split(".")[0],
                preview=preview,
                asset_uri=asset_path,
                asat=asat,
            )
        )
    return threads


async def poll_batch(poll_fn, description: str):
    """Poll *poll_fn* until it returns a non-None result."""
    print(f"Polling every {POLL_INTERVAL_SECS}s (max {POLL_MAX_ATTEMPTS} attempts)…")
    for attempt in range(1, POLL_MAX_ATTEMPTS + 1):
        result = await poll_fn()
        if result is not None:
            return result
        print(f"  [{attempt}/{POLL_MAX_ATTEMPTS}] {description} still running…")
        time.sleep(POLL_INTERVAL_SECS)
    return None


async def main() -> None:
    threads = load_threads_from_instagram()
    print(f"Loaded {len(threads)} threads from Instagram stories")

    builder = MemoryPromptBuilder(cast(list[Thread], threads))
    prompts = builder.build()
    print(f"Built {len(prompts)} prompt(s)")
    for p in prompts:
        print(f"  {p.item_id}: {len(p.asset_paths)} asset(s)")

    client = LLMClient(
        model=OpenAIModel.GPT_4O,
        api_key=os.environ["OPENAI_API_KEY"],
        embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_SMALL,
    )

    job_key = await client.batch_submit("smoke-batch-test", prompts)
    print(f"\nBatch job submitted: {job_key}")
    print(f"Polling every {POLL_INTERVAL_SECS}s (max {POLL_MAX_ATTEMPTS} attempts)…")

    results = None
    for attempt in range(1, POLL_MAX_ATTEMPTS + 1):
        results = await client.batch_get_results(job_key, MemorySchema)
        if results is not None:
            break
        print(f"  [{attempt}/{POLL_MAX_ATTEMPTS}] still running…")
        time.sleep(POLL_INTERVAL_SECS)

    # --- Step 1: Generate memories via batch ---
    print("\n=== Step 1: Memory generation ===")
    gen_job = await client.batch_submit("smoke-batch-test", prompts)
    print(f"Batch job submitted: {gen_job}")

    results = await poll_batch(
        lambda: client.batch_get_results(gen_job, MemorySchema),
        "generation",
    )

    if not results:
        print("\nNo generation results (timed out or empty).")
        return

    all_memories: list[tuple[str, str]] = []
    print(f"\nMemories generated for {len(results)} day(s):")
    for day, schema in sorted(results.items()):
        print(f"\n  {day}:")
        for m in schema.memories:
            print(f"    - {m.content}")
            all_memories.append((str(uuid.uuid4()), m.content))

    # --- Step 2: Embed memories via batch ---
    print(f"\n=== Step 2: Embedding {len(all_memories)} memories ===")
    embed_items = [EmbedItem(item_id=mid, text=text) for mid, text in all_memories]

    embed_job = await client.embed_batch_submit("smoke-embed-test", embed_items)
    print(f"Embed batch job submitted: {embed_job}")

    embeddings = await poll_batch(
        lambda: client.embed_batch_get_results(embed_job),
        "embedding",
    )

    if not embeddings:
        print("\nNo embedding results (timed out or empty).")
        return

    print(f"\nEmbeddings received for {len(embeddings)} memories:")
    for mid, _ in all_memories:
        vec = embeddings.get(mid)
        if vec:
            print(f"  {mid[:8]}… dim={len(vec)} first3={vec[:3]}")
        else:
            print(f"  {mid[:8]}… MISSING")


if __name__ == "__main__":
    asyncio.run(main())

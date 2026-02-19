"""Smoke-test: load real Instagram data → MemoryPromptBuilder → GeminiBatchClient."""

import asyncio
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from context_use.etl.models.thread import Thread
from context_use.llm import LLMClient, OpenAIModel
from context_use.memories.prompt import MemoryPromptBuilder, MemorySchema

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    if results:
        print(f"\nMemories generated for {len(results)} day(s):")
        for day, schema in sorted(results.items()):
            print(f"\n  {day}:")
            for m in schema.memories:
                print(f"    - {m.content}")
    else:
        print("\nNo results returned (timed out or empty).")


if __name__ == "__main__":
    asyncio.run(main())

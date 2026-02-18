"""Smoke-test: load real Instagram data → MemoryPromptBuilder → GeminiClient."""

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from google import genai

from context_use.llm.gemini import GeminiClient
from context_use.memories.prompt import MemoryPromptBuilder, MemorySchema

logging.basicConfig(level=logging.INFO)

DATA_ROOT = Path("data/616493c0-d385-42bc-96ce-ea2a7b90c49d")
STORIES_JSON = DATA_ROOT / "your_instagram_activity/media/stories.json"

MAX_THREADS = 10


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


threads = load_threads_from_instagram()
print(f"Loaded {len(threads)} threads from Instagram stories")

builder = MemoryPromptBuilder(threads)
prompts = builder.build()

print(f"Built {len(prompts)} prompt(s)")
for p in prompts:
    print(f"  {p.item_id}: {len(p.asset_paths)} asset(s)")

client = GeminiClient(
    genai_client=genai.Client(api_key=os.environ["GEMINI_API_KEY"]),
    model="gemini-2.5-flash",
)

job_key = client.batch_submit("test-batch", prompts)
results = client.batch_get_results(job_key, MemorySchema)

if results:
    print(f"\nMemories generated for {len(results)} day(s):")
    for day, schema in sorted(results.items()):
        print(f"\n  {day}:")
        for m in schema.memories:
            print(f"    - {m.content}")
else:
    print("\nNo results returned.")

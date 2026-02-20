"""E2E: generate a user profile from existing memories in DB.

Loads all active memories, sends them to the LLM, and writes the
resulting markdown profile to a file.

Usage:
    uv run tests/e2e_profile.py
    uv run tests/e2e_profile.py --lookback 12     # 12-month window
    uv run tests/e2e_profile.py --out profile.md   # custom output path
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from context_use.db.models import Base
from context_use.db.postgres import PostgresBackend
from context_use.llm import LLMClient, OpenAIEmbeddingModel, OpenAIModel
from context_use.memories.models import MemoryStatus, TapestryMemory
from context_use.profile.generator import generate_profile
from context_use.profile.models import TapestryProfile  # noqa: F401 — registers model

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


async def main() -> None:
    parser = argparse.ArgumentParser(description="E2E profile generation")
    parser.add_argument(
        "--lookback",
        type=int,
        default=6,
        help="Lookback window in months (default: 6)",
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        help="Output file path (default: data/profiles/profile_<timestamp>.md)",
    )
    args = parser.parse_args()

    db = get_db()

    async with db.get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    llm_client = LLMClient(
        model=OpenAIModel.GPT_4O,
        api_key=os.environ["OPENAI_API_KEY"],
        embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
    )

    session = db.get_session()
    try:
        count_stmt = select(func.count()).where(
            TapestryMemory.status == MemoryStatus.active.value,
        )
        total = (await session.execute(count_stmt)).scalar() or 0
        print(f"\n{total} active memories")

        if total == 0:
            print("No memories found. Run the memories pipeline first.")
            return

        print(f"\nGenerating profile (lookback={args.lookback} months)...")
        profile = await generate_profile(
            session,
            llm_client,
            lookback_months=args.lookback,
        )
        await session.commit()

        # Write to file
        out_dir = Path("data/profiles")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        out_path = Path(args.out) if args.out else out_dir / f"profile_{ts}.md"
        out_path.write_text(profile.content, encoding="utf-8")

        print(f"\n{'=' * 60}")
        print(profile.content)
        print(f"{'=' * 60}")
        print(f"\nProfile written to {out_path}")
        print(
            f"  Generated at: {profile.generated_at}"
            f"\n  Memory count: {profile.memory_count}"
            f"\n  Length: {len(profile.content)} chars"
        )

    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())

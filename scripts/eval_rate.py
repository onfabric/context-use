#!/usr/bin/env python3
"""Interactive memory rating tool.

Loads memories from the store or runs fresh extraction, shows them one
at a time, and collects human ratings (1-5). Optionally runs the LLM
judge alongside so you can compare.

Saves ratings to a JSON file. Run again with the same output file to
resume where you left off.

Usage:
    uv run scripts/eval_rate.py                            # rate from store
    uv run scripts/eval_rate.py --extract                  # extract then rate
    uv run scripts/eval_rate.py --extract --threads 30     # smaller sample
    uv run scripts/eval_rate.py --with-llm-judge           # also show LLM scores
    uv run scripts/eval_rate.py --output my_ratings.json   # custom output path
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from context_use.eval.metrics import entity_count


@dataclass
class RatableMemory:
    id: str
    content: str
    from_date: str
    to_date: str


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Interactively rate memory quality")
    p.add_argument("--extract", action="store_true", help="Run fresh extraction instead of loading from store")
    p.add_argument("--threads", type=int, default=50, help="Max threads to sample (with --extract)")
    p.add_argument("--interaction-type", help="Filter to one interaction type")
    p.add_argument("--output", type=str, default="eval_ratings.json", help="Path to save ratings")
    p.add_argument("--limit", type=int, help="Max memories to rate")
    p.add_argument("--with-llm-judge", action="store_true", help="Also run LLM judge on each memory")
    p.add_argument("--shuffle", action="store_true", help="Randomize memory order")
    return p.parse_args()


def _load_existing_ratings(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    with open(path) as f:
        data = json.load(f)
    return {r["id"]: r["human_rating"] for r in data.get("ratings", [])}


def _print_analysis(ratings: list[dict]) -> None:
    rated = [r for r in ratings if r.get("human_rating") is not None]
    if not rated:
        print("No ratings collected.")
        return

    scores = [r["human_rating"] for r in rated]
    print(f"\n{'═' * 60}")
    print(f"  Rated {len(rated)} memories")
    print(f"{'═' * 60}")

    dist = defaultdict(int)
    for s in scores:
        dist[s] += 1
    bar = "  ".join(f"{k}★={dist[k]}" for k in sorted(dist))
    print(f"\n  Distribution: {bar}")
    print(f"  Average human rating: {mean(scores):.2f}")

    print(f"\n  {'Tier':<8} {'Count':>5}  {'Entities':>8}  {'Length':>8}  {'LLM Judge':>9}")
    print(f"  {'─' * 46}")
    for tier in range(1, 6):
        tier_items = [r for r in rated if r["human_rating"] == tier]
        if not tier_items:
            continue
        avg_ent = mean(r["entity_count"] for r in tier_items)
        avg_len = mean(r["content_length"] for r in tier_items)
        llm_scores = [r["llm_score"] for r in tier_items if r.get("llm_score") is not None]
        llm_str = f"{mean(llm_scores):.1f}" if llm_scores else "—"
        print(f"  {tier}★{'':<5} {len(tier_items):>5}  {avg_ent:>8.1f}  {avg_len:>8.0f}  {llm_str:>9}")

    print()


async def _load_from_store(ctx) -> list[RatableMemory]:  # noqa: ANN001
    from context_use.models.memory import MemoryStatus

    memories = await ctx._store.list_memories(status=MemoryStatus.active.value)
    return [
        RatableMemory(
            id=m.id,
            content=m.content,
            from_date=str(m.from_date),
            to_date=str(m.to_date),
        )
        for m in memories
    ]


async def _load_from_extraction(ctx, args) -> list[RatableMemory]:  # noqa: ANN001
    from context_use.eval.runner import run_extraction

    interaction_types = [args.interaction_type] if args.interaction_type else None
    threads = await ctx._store.list_threads(
        interaction_types=interaction_types,
        limit=args.threads,
        random=True,
    )
    if not threads:
        print("No threads found. Run 'context-use ingest' first.")
        sys.exit(1)

    print(f"  Sampled {len(threads)} threads, running extraction...")
    extraction = await run_extraction(threads, ctx._llm_client)
    print(f"  Extracted {len(extraction.all_memories)} memories\n")

    return [
        RatableMemory(
            id=f"extract-{i}",
            content=m.content,
            from_date=m.from_date,
            to_date=m.to_date,
        )
        for i, m in enumerate(extraction.all_memories)
    ]


async def main() -> None:
    args = _parse_args()
    output_path = Path(args.output)

    from context_use.config import build_ctx, load_config

    cfg = load_config()
    needs_llm = args.extract or args.with_llm_judge

    if needs_llm and not cfg.openai_api_key:
        print("No API key configured. Set OPENAI_API_KEY or run 'context-use config set-key'.")
        sys.exit(1)

    ctx = build_ctx(cfg, llm_mode="sync" if needs_llm else "batch")
    await ctx.init()

    if args.extract:
        memories = await _load_from_extraction(ctx, args)
    else:
        memories = await _load_from_store(ctx)

    if not memories:
        print("No memories found. Run 'context-use pipeline' first, or use --extract.")
        sys.exit(1)

    if args.shuffle:
        import random
        random.shuffle(memories)

    if args.limit:
        memories = memories[: args.limit]

    existing = _load_existing_ratings(output_path)
    unrated = [m for m in memories if m.id not in existing]

    print(f"  {len(memories)} memories loaded, {len(existing)} already rated, {len(unrated)} to go\n")

    if not unrated:
        print("All memories already rated. Loading existing ratings for analysis.")
        all_ratings = []
        for m in memories:
            if m.id in existing:
                all_ratings.append({
                    "id": m.id,
                    "content": m.content,
                    "from_date": m.from_date,
                    "to_date": m.to_date,
                    "human_rating": existing[m.id],
                    "entity_count": entity_count(m.content),
                    "content_length": len(m.content),
                    "llm_score": None,
                })
        _print_analysis(all_ratings)
        return

    llm_judgments: dict[int, int] = {}
    if args.with_llm_judge:
        from context_use.eval.llm_judge import judge_memories

        print("  Running LLM judge on all memories (batched)...")
        judgments = await judge_memories(memories, ctx._llm_client)
        for j in judgments:
            llm_judgments[j.index] = j.score
        print(f"  Got {len(judgments)} LLM judgments\n")

    all_ratings: list[dict] = []
    for m in memories:
        if m.id in existing:
            all_ratings.append({
                "id": m.id,
                "content": m.content,
                "from_date": m.from_date,
                "to_date": m.to_date,
                "human_rating": existing[m.id],
                "entity_count": entity_count(m.content),
                "content_length": len(m.content),
                "llm_score": None,
            })

    mem_index_map = {m.id: i for i, m in enumerate(memories)}

    for pos, m in enumerate(unrated, 1):
        entities = entity_count(m.content)
        llm_score = llm_judgments.get(mem_index_map.get(m.id, -1))

        print(f"  Memory {pos}/{len(unrated)}")
        print(f"  {'─' * 56}")
        print(f"  Period: {m.from_date} → {m.to_date}")
        print(f"  {m.content}")
        print()
        print(f"  Auto: entities={entities}  length={len(m.content)}", end="")
        if llm_score is not None:
            print(f"  llm_judge={llm_score}★", end="")
        print()
        print(f"  {'─' * 56}")

        while True:
            try:
                inp = input("  Rate (1-5, s=skip, q=quit): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                inp = "q"

            if inp == "q":
                break
            if inp == "s":
                break
            if inp in ("1", "2", "3", "4", "5"):
                rating = int(inp)
                all_ratings.append({
                    "id": m.id,
                    "content": m.content,
                    "from_date": m.from_date,
                    "to_date": m.to_date,
                    "human_rating": rating,
                    "entity_count": entities,
                    "content_length": len(m.content),
                    "llm_score": llm_score,
                })
                print()
                break
            print("  Invalid input. Enter 1-5, s, or q.")

        if inp == "q":
            print()
            break

    with open(output_path, "w") as f:
        json.dump({"ratings": all_ratings}, f, indent=2)
    print(f"  Saved {len(all_ratings)} ratings to {output_path}")

    _print_analysis(all_ratings)


if __name__ == "__main__":
    asyncio.run(main())

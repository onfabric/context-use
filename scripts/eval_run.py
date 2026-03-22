#!/usr/bin/env python3
"""Score existing memories from the store, or run fresh extraction and score.

Usage:
    uv run scripts/eval_run.py                         # score existing memories
    uv run scripts/eval_run.py --extract               # run fresh extraction + score
    uv run scripts/eval_run.py --extract --threads 20  # smaller sample
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate memory extraction quality")
    p.add_argument(
        "--extract",
        action="store_true",
        help="Run fresh extraction instead of scoring existing memories",
    )
    p.add_argument(
        "--threads", type=int, default=50, help="Max threads to sample (with --extract)"
    )
    p.add_argument("--interaction-type", help="Filter to one interaction type")
    return p.parse_args()


def _print_metrics(metrics) -> None:  # noqa: ANN001
    print(f"\n{'─' * 50}")
    print(f"  Memories scored:        {metrics.memory_count}")
    print(f"  Structural validity:    {metrics.structural_validity:.0%}")
    print(f"  Length in range:        {metrics.length_ok_ratio:.0%}")
    print(f"  Entity density:         {metrics.entity_density:.2f} (informational)")
    print(f"  Avg content length:     {metrics.avg_content_length:.0f} chars")
    print(f"  Median content length:  {metrics.median_content_length:.0f} chars")
    print(f"{'─' * 50}")
    print(f"  Quality score:          {metrics.quality_score:.4f}")
    print(f"{'─' * 50}")


async def _score_existing(cfg, ctx, args) -> None:  # noqa: ANN001
    from context_use.eval.metrics import score_memories
    from context_use.models.memory import MemoryStatus

    print("\nScoring existing memories from the store...")
    memories = await ctx._store.list_memories(status=MemoryStatus.active.value)

    if not memories:
        print(
            "No memories in store. Run 'context-use pipeline' first, or use --extract."
        )
        sys.exit(1)

    print(f"Found {len(memories)} active memories")
    metrics = score_memories(memories)  # type: ignore[arg-type]
    _print_metrics(metrics)

    print("\nSample memories:")
    for m in memories[:5]:
        preview = m.content[:120] + "…" if len(m.content) > 120 else m.content
        print(f"  [{m.from_date}] {preview}")
    print()


async def _run_extraction(cfg, ctx, args) -> None:  # noqa: ANN001
    from context_use.eval.metrics import score_memories
    from context_use.eval.runner import run_extraction

    interaction_types = [args.interaction_type] if args.interaction_type else None

    print("\nSampling threads from the store...")
    threads = await ctx._store.list_threads(
        interaction_types=interaction_types,
        limit=args.threads,
        random=True,
    )

    if not threads:
        print("No threads found. Run 'context-use ingest' first.")
        sys.exit(1)

    type_counts: dict[str, int] = {}
    for t in threads:
        type_counts[t.interaction_type] = type_counts.get(t.interaction_type, 0) + 1

    print(f"Sampled {len(threads)} threads:")
    for itype, count in sorted(type_counts.items()):
        print(f"  {itype}: {count}")

    print("\nRunning extraction (sync mode)...")
    extraction = await run_extraction(threads, ctx._llm_client)

    if not extraction.all_memories:
        print("No memories extracted.")
        sys.exit(1)

    print(
        f"\nExtracted {len(extraction.all_memories)} memories from {len(extraction.results)} groups"  # noqa: E501
    )
    metrics = score_memories(extraction.all_memories)
    _print_metrics(metrics)

    print("\nSample memories:")
    for m in extraction.all_memories[:5]:
        preview = m.content[:120] + "…" if len(m.content) > 120 else m.content
        print(f"  [{m.from_date}] {preview}")
    print()


async def main() -> None:
    args = _parse_args()

    from context_use.cli.config import build_ctx, load_config

    cfg = load_config()
    llm_mode = "sync" if args.extract else "batch"

    if args.extract and not cfg.openai_api_key:
        print(
            "No API key configured. Set OPENAI_API_KEY or run 'context-use config set-key'."  # noqa: E501
        )
        sys.exit(1)

    ctx = build_ctx(cfg, llm_mode=llm_mode)
    await ctx.init()

    if args.extract:
        await _run_extraction(cfg, ctx, args)
    else:
        await _score_existing(cfg, ctx, args)


if __name__ == "__main__":
    asyncio.run(main())

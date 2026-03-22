#!/usr/bin/env python3
"""Autoresearch loop: iteratively mutate the extraction prompt to improve quality.

The loop:
  1. Samples eval threads (fixed across iterations).
  2. Runs baseline extraction → judges with calibrated LLM judge.
  3. Asks an LLM to propose a prompt mutation based on the current prompt,
     judge score, and sample memories.
  4. Runs extraction with the mutated prompt → judges again.
  5. If the judge score improves, keeps the mutation. Otherwise, reverts.
  6. Repeats for N iterations.

Usage:
    uv run scripts/eval_loop.py                          # 3 iterations, 50 threads
    uv run scripts/eval_loop.py --iterations 5           # more iterations
    uv run scripts/eval_loop.py --threads 30             # smaller sample
    uv run scripts/eval_loop.py --output prompt_log.jsonl # save iteration history
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from context_use.eval.llm_judge import judge_memories, mean_judge_score
from context_use.eval.runner import ExtractionRun, run_extraction
from context_use.llm.base import BaseLLMClient
from context_use.models.thread import Thread

_MUTATION_SYSTEM_PROMPT = """\
You are a prompt engineer optimizing an LLM prompt that extracts personal \
memories from conversation transcripts.

You will be given:
- The current prompt body (the instruction section sent to the LLM before each transcript).
- The judge score from an LLM judge calibrated on human ratings.
- A sample of extracted memories with their individual judge scores.

Your job: propose an improved version of the prompt body that should produce \
higher-quality memories. A good memory reveals something meaningful about \
who the person is. Focus on:
- Personal significance: feelings, motivations, relationships, identity facts.
- The right level of abstraction: "I work with Docker" not "I ran docker ps."
- Suppressing procedural noise: commands, error messages, and API details \
are not memories.
- Keeping the first-person journal-entry style.

Rules:
- Return ONLY the new prompt body text. No explanation, no markdown fences.
- Keep the same overall structure (sections for task, what to capture, \
level of abstraction, what makes a good memory, what to avoid).
- Do not change the output format section — it will be appended automatically.
- Be bold with changes but stay grounded in what makes a good memory.
- The prompt must still work for any conversation topic (not just the samples).
"""  # noqa: E501


def _format_mutation_prompt(
    current_body: str,
    judge_score: float,
    sample_memories: list[tuple[str, int | None]],
) -> str:
    samples = "\n".join(
        f"  - [{score}★] {text}" if score is not None else f"  - {text}"
        for text, score in sample_memories[:10]
    )
    return f"""\
## Current prompt body

{current_body}

## Current judge score

{judge_score:.2f} / 5.00  (calibrated on human ratings)

## Sample extracted memories (with judge scores)

{samples}

## Your task

Produce an improved prompt body. Return ONLY the prompt text, nothing else.
"""


async def _propose_mutation(
    llm: BaseLLMClient,
    current_body: str,
    judge_score: float,
    sample_memories: list[tuple[str, int | None]],
) -> str:
    prompt = (
        _MUTATION_SYSTEM_PROMPT
        + "\n---\n\n"
        + _format_mutation_prompt(current_body, judge_score, sample_memories)
    )
    return await llm.completion(prompt)


async def _judge_run(
    run: ExtractionRun, llm: BaseLLMClient
) -> tuple[float, dict[int, int]]:
    judgments = await judge_memories(run.all_memories, llm)
    score = mean_judge_score(judgments)
    by_index = {j.index: j.score for j in judgments}
    return score, by_index


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Autoresearch loop for memory extraction prompts"
    )
    p.add_argument(
        "--iterations", type=int, default=3, help="Number of mutation iterations"
    )
    p.add_argument("--threads", type=int, default=50, help="Max threads to sample")
    p.add_argument("--interaction-type", help="Filter to one interaction type")
    p.add_argument("--output", type=str, help="Path to save iteration log (JSONL)")
    return p.parse_args()


def _log_iteration(
    path: Path,
    iteration: int,
    judge_score: float,
    memory_count: int,
    accepted: bool,
    prompt_body: str,
) -> None:
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "iteration": iteration,
        "judge_score": judge_score,
        "memory_count": memory_count,
        "accepted": accepted,
        "prompt_body": prompt_body,
    }
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _print_comparison(label: str, judge_score: float, memory_count: int) -> None:
    print(f"  [{label}] judge={judge_score:.2f}/5  memories={memory_count}")


async def main() -> None:
    args = _parse_args()

    from context_use.cli.config import build_ctx, load_config

    cfg = load_config()

    ctx = build_ctx(cfg, llm_mode="sync")
    await ctx.init()

    log_path = Path(args.output) if args.output else None
    interaction_types = [args.interaction_type] if args.interaction_type else None

    async def _sample_threads() -> list[Thread]:
        t = await ctx._store.list_threads(
            interaction_types=interaction_types,
            limit=args.threads,
            random=True,
        )
        if not t:
            print("No threads found. Run 'context-use ingest' first.")
            sys.exit(1)
        return t

    print("Running baseline on a random thread sample...")
    threads = await _sample_threads()
    print(f"  Sampled {len(threads)} threads")

    baseline = await run_extraction(threads, ctx._llm_client)
    if not baseline.all_memories:
        print("Baseline produced no memories. Check thread data / provider configs.")
        sys.exit(1)

    print("  Judging baseline memories...")
    best_score, best_judgments = await _judge_run(baseline, ctx._llm_client)
    best_body = baseline.prompt_body
    best_count = len(baseline.all_memories)

    print("\nBaseline:")
    _print_comparison("baseline", best_score, best_count)

    if log_path:
        _log_iteration(log_path, 0, best_score, best_count, True, best_body)

    current_memories = baseline.all_memories
    current_judgments = best_judgments

    for i in range(1, args.iterations + 1):
        print(f"\n{'═' * 60}")
        print(f"  Iteration {i}/{args.iterations}")
        print(f"{'═' * 60}")

        sample_with_scores: list[tuple[str, int | None]] = [
            (m.content, current_judgments.get(idx))
            for idx, m in enumerate(current_memories[:10])
        ]

        print("  Proposing mutation...")
        mutated_body = await _propose_mutation(
            ctx._llm_client,
            best_body,
            best_score,
            sample_with_scores,
        )

        threads = await _sample_threads()
        print(f"  Fresh sample: {len(threads)} threads")

        print("  Running current-best on fresh sample...")
        best_run = await run_extraction(threads, ctx._llm_client, prompt_body=best_body)
        print("  Running mutation on same sample...")
        mutated_run = await run_extraction(
            threads,
            ctx._llm_client,
            prompt_body=mutated_body,
        )

        if not best_run.all_memories or not mutated_run.all_memories:
            print("  One of the runs produced no memories — skipping.")
            if log_path:
                _log_iteration(log_path, i, 0.0, 0, False, mutated_body)
            continue

        print("  Judging both runs...")
        current_score, _ = await _judge_run(best_run, ctx._llm_client)
        mutated_score, mutated_judgments = await _judge_run(
            mutated_run, ctx._llm_client
        )

        _print_comparison("current best", current_score, len(best_run.all_memories))
        _print_comparison("mutation", mutated_score, len(mutated_run.all_memories))

        accepted = mutated_score > current_score
        if accepted:
            delta = mutated_score - current_score
            print(f"  ✓ Accepted (+{delta:.2f})")
            best_score = mutated_score
            best_body = mutated_body
            best_count = len(mutated_run.all_memories)
            current_memories = mutated_run.all_memories
            current_judgments = mutated_judgments
        else:
            delta = mutated_score - current_score
            print(f"  ✗ Rejected ({delta:+.2f})")

        if log_path:
            _log_iteration(
                log_path,
                i,
                mutated_score,
                len(mutated_run.all_memories),
                accepted,
                mutated_body,
            )

    print(f"\n{'═' * 60}")
    print(f"  Final results after {args.iterations} iterations")
    print(f"{'═' * 60}")
    _print_comparison("final best", best_score, best_count)
    print()

    if best_body != baseline.prompt_body:
        from context_use.eval.prompt_io import save_prompt_body

        diff = difflib.unified_diff(
            baseline.prompt_body.splitlines(keepends=True),
            best_body.splitlines(keepends=True),
            fromfile="baseline",
            tofile="improved",
        )
        print("".join(diff))

        path = save_prompt_body(best_body)
        print(f"  Improved prompt saved to: {path}")
        print("  The pipeline will use this prompt on next run.")
        print("  Delete the file to revert to the default prompt.")
    else:
        print("  No improvements found — baseline prompt unchanged.")


if __name__ == "__main__":
    asyncio.run(main())

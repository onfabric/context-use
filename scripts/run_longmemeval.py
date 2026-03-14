"""Run the LongMemEval benchmark and print accuracy results.

Usage:
    uv run python scripts/run_longmemeval.py \\
        --dataset path/to/longmemeval.json \\
        --api-key sk-... \\
        [--model openai/gpt-4o] \\
        [--embedding-model openai/text-embedding-3-large] \\
        [--top-k 10] \\
        [--no-memories] \\
        [--output results.jsonl] \\
        [--question-ids q001 q002 ...]

The dataset JSON can be downloaded from:
    https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from context_use.llm.litellm import LiteLLMSyncClient
from context_use.llm.models import OpenAIEmbeddingModel, OpenAIModel
from context_use.store.sqlite import SqliteStore
from evals.longmemeval.dataset import LongMemEvalDataset
from evals.longmemeval.runner import LongMemEvalRunner, RunConfig


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the LongMemEval benchmark.")
    parser.add_argument("--dataset", required=True, help="Path to the dataset JSON file.")
    parser.add_argument("--api-key", required=True, help="OpenAI API key.")
    parser.add_argument(
        "--model",
        default=OpenAIModel.GPT_4O,
        choices=list(OpenAIModel),
        help="LLM model for answering and judging (default: openai/gpt-4o).",
    )
    parser.add_argument(
        "--embedding-model",
        default=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
        choices=list(OpenAIEmbeddingModel),
        help="Embedding model for memory search.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of memories to retrieve per question (default: 10).",
    )
    parser.add_argument(
        "--no-memories",
        action="store_true",
        help="Skip memory generation and fall back to raw thread retrieval.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write per-question results as JSONL.",
    )
    parser.add_argument(
        "--question-ids",
        nargs="*",
        default=[],
        metavar="ID",
        help="Evaluate only these question IDs (default: all).",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    dataset = LongMemEvalDataset.from_file(args.dataset)
    print(f"Loaded {len(dataset)} questions from {args.dataset}")

    llm_client = LiteLLMSyncClient(
        model=OpenAIModel(args.model),
        api_key=args.api_key,
        embedding_model=OpenAIEmbeddingModel(args.embedding_model),
    )

    config = RunConfig(
        top_k=args.top_k,
        generate_memories=not args.no_memories,
        output_path=args.output,
        question_ids=args.question_ids,
    )

    runner = LongMemEvalRunner(
        store_factory=lambda: SqliteStore(path=":memory:"),
        llm_client=llm_client,
        config=config,
    )

    results, metrics = await runner.run_and_judge(dataset)

    print(f"\nResults ({len(results)} questions evaluated):")
    print(f"  Overall accuracy: {metrics.accuracy:.1%} ({metrics.correct}/{metrics.total})")

    if metrics.by_type:
        print("\n  By question type:")
        for qtype, tm in sorted(metrics.by_type.items()):
            print(f"    {qtype}: {tm.accuracy:.1%} ({tm.correct}/{tm.total})")

    if args.output:
        print(f"\nPer-question results written to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())

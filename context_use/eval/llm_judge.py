from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean

from context_use.eval.metrics import Scorable, entity_count
from context_use.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)

_SYNTHESIS_PROBE_PROMPT = """\
You have access to a set of personal memories about someone. Based on \
these memories, write a detailed profile covering their:

- Work and professional life
- Technical projects and tools
- Physical activity and hobbies
- Social life and relationships
- Travel and places
- Daily routines and habits

Be as specific as possible. Use exact names, dates, tools, places, and \
events from the memories. If you don't have information about a category, \
skip it entirely.

## Memories

{memories}

## Profile
"""

_JUDGE_PROMPT = """\
Rate each personal memory below on a 1–5 scale. The question is: \
**does this tell me something meaningful about who this person is?**

A good memory reveals identity, feelings, relationships, interests, or \
life circumstances. A bad memory is procedural noise — specific commands, \
error messages, or "how to do X" lookups that anyone could have.

Here are calibration examples from a human rater:

5★ "I have feelings for someone in my friend group and I'm unsure how \
to handle the situation." — deeply personal feeling
5★ "I live in Barcelona and I'm trying to get to a coastal town without \
a car." — identity fact (location) + travel plan
5★ "I was learning Go by comparing its concurrency model to what I knew \
from Python, trying to understand goroutines vs threads." — meaningful \
learning journey, reveals skill background
4★ "I've been reading about marine biology — I asked about bioluminescence \
in deep-sea fish." — a curiosity / learning interest
4★ "I was researching whether large automakers handle payroll in-house \
or outsource it." — work-related research, reveals professional context
3★ "I was building a Flask app connected to Postgres and debugging \
connection pooling." — reveals a project but too focused on debugging details
2★ "I tried to start a Redis container and exec into it, but got \
'No such container' because I forgot to name it." — procedural debugging noise
2★ "I needed to run only a single test file in pytest instead of the \
full suite." — procedural "how to" lookup

Key patterns:
- Personal feelings, social situations, identity facts → 5★
- Curiosities, learning interests, work context → 4★
- Technical work that reveals a project but is too detailed → 3★
- Specific commands, errors, "how do I do X" → 2★
- Completely vague filler ("had a productive session") → 1★

Return a JSON array where each element is {{"index": <0-based>, "score": <1-5>}}.
Return ONLY the JSON array, nothing else.

## Memories

{memories}
"""


@dataclass(frozen=True)
class SynthesisProbeResult:
    profile: str
    entity_count: int
    word_count: int
    entity_rate: float


@dataclass(frozen=True)
class MemoryJudgment:
    index: int
    score: int


def mean_judge_score(judgments: list[MemoryJudgment]) -> float:
    if not judgments:
        return 0.0
    return mean(j.score for j in judgments)


async def synthesis_probe(
    memories: Sequence[Scorable],
    llm: BaseLLMClient,
) -> SynthesisProbeResult:
    mem_lines = [
        f"- [{m.from_date} → {m.to_date}] {m.content}"
        for m in memories
    ]
    prompt = _SYNTHESIS_PROBE_PROMPT.format(memories="\n".join(mem_lines))
    profile = await llm.completion(prompt)

    entities = entity_count(profile)
    words = len(profile.split())

    return SynthesisProbeResult(
        profile=profile,
        entity_count=entities,
        word_count=words,
        entity_rate=entities / max(words, 1),
    )


async def judge_memories(
    memories: Sequence[Scorable],
    llm: BaseLLMClient,
    *,
    batch_size: int = 15,
) -> list[MemoryJudgment]:
    judgments: list[MemoryJudgment] = []

    for batch_start in range(0, len(memories), batch_size):
        batch = list(memories[batch_start : batch_start + batch_size])
        numbered = "\n".join(
            f"{i}. [{m.from_date} → {m.to_date}] {m.content}"
            for i, m in enumerate(batch)
        )
        prompt = _JUDGE_PROMPT.format(memories=numbered)

        try:
            raw = await llm.completion(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            parsed = json.loads(raw)
            for item in parsed:
                judgments.append(MemoryJudgment(
                    index=batch_start + int(item["index"]),
                    score=max(1, min(5, int(item["score"]))),
                ))
        except Exception:
            logger.warning(
                "Failed to parse LLM judge response for batch starting at %d",
                batch_start,
                exc_info=True,
            )

    return judgments

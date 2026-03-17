from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field, replace

from context_use.llm.base import BaseLLMClient
from context_use.memories.prompt.base import GroupContext, Memory, MemorySchema
from context_use.models.thread import Thread

logger = logging.getLogger(__name__)

_TRANSCRIPT_MARKER = "## Transcript\n"


@dataclass
class GroupResult:
    group_id: str
    interaction_type: str
    thread_count: int
    memories: list[Memory] = field(default_factory=list)


@dataclass
class ExtractionRun:
    results: list[GroupResult] = field(default_factory=list)
    prompt_body: str = ""

    @property
    def all_memories(self) -> list[Memory]:
        return [m for r in self.results for m in r.memories]

    @property
    def total_threads(self) -> int:
        return sum(r.thread_count for r in self.results)


def _replace_prompt_body(prompt: str, new_body: str) -> str:
    idx = prompt.index(_TRANSCRIPT_MARKER)
    return new_body.rstrip() + "\n\n" + prompt[idx:]


def _extract_prompt_body(prompt: str) -> str:
    idx = prompt.index(_TRANSCRIPT_MARKER)
    return prompt[:idx].rstrip()


async def run_extraction(
    threads: list[Thread],
    llm_client: BaseLLMClient,
    *,
    prompt_body: str | None = None,
) -> ExtractionRun:
    from context_use.providers.registry import get_memory_config

    by_type: dict[str, list[Thread]] = defaultdict(list)
    for t in threads:
        by_type[t.interaction_type].append(t)

    run = ExtractionRun()
    captured_body = False

    for interaction_type, type_threads in by_type.items():
        try:
            config = get_memory_config(interaction_type)
        except KeyError:
            logger.info("No memory config for %s, skipping", interaction_type)
            continue

        grouper = config.create_grouper()
        groups = grouper.group(type_threads)

        contexts = [
            GroupContext(group_id=g.group_id, new_threads=g.threads)
            for g in groups
        ]

        builder = config.create_prompt_builder(contexts)
        if not builder.has_content():
            continue

        prompts = builder.build()

        for prompt_item in prompts:
            if not captured_body:
                run.prompt_body = _extract_prompt_body(prompt_item.prompt)
                captured_body = True

            if prompt_body is not None:
                prompt_item = replace(
                    prompt_item,
                    prompt=_replace_prompt_body(prompt_item.prompt, prompt_body),
                )

            try:
                schema = await llm_client.structured_completion(
                    prompt_item, MemorySchema
                )
                group_result = GroupResult(
                    group_id=prompt_item.item_id,
                    interaction_type=interaction_type,
                    thread_count=len(
                        next(
                            (g.threads for g in groups if g.group_id == prompt_item.item_id),
                            [],
                        )
                    ),
                    memories=schema.memories,
                )
                run.results.append(group_result)
            except Exception:
                logger.error(
                    "Extraction failed for group %s",
                    prompt_item.item_id,
                    exc_info=True,
                )

    return run

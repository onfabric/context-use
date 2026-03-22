from __future__ import annotations

from dataclasses import dataclass

from context_use.batch.grouper import ThreadGroup
from context_use.memories.prompt.base import GroupContext

RELEVANT_PROFILE = """\
Software engineer and founder building context portability infrastructure \
for AI agents. I love fresh and healthy food.
"""

IRRELEVANT_PROFILE = """\
Retired primary school teacher living in rural Wales. Enjoys watercolour painting, \
tending an allotment, and baking sourdough. Has no interest in technology beyond \
a basic smartphone for calls and photos.\
"""

RELEVANT_MEMORIES = [
    "I'm trying to figure out how to approach prosumer go-to-market for Fabric",
    "I'm a long time Rust developer but recently i started using Python",
    "I eat pizza at least once a week but only if it's really good quality",
]


@dataclass
class EvalScenario:
    id: str
    description: str
    contexts: list[GroupContext]


def make_scenarios(groups: list[ThreadGroup]) -> list[EvalScenario]:
    def base_contexts(
        *,
        user_profile: str | None = None,
        relevant_memories: list[str] | None = None,
    ) -> list[GroupContext]:
        return [
            GroupContext(
                group_id=g.group_id,
                new_threads=g.threads,
                user_profile=user_profile,
                relevant_memories=relevant_memories or [],
            )
            for g in groups
        ]

    return [
        EvalScenario(
            id="baseline",
            description="No extra context — pure thread content",
            contexts=base_contexts(),
        ),
        EvalScenario(
            id="relevant_profile",
            description="Relevant user profile injected",
            contexts=base_contexts(user_profile=RELEVANT_PROFILE),
        ),
        EvalScenario(
            id="relevant_memories",
            description="Relevant memories injected",
            contexts=base_contexts(relevant_memories=RELEVANT_MEMORIES),
        ),
        EvalScenario(
            id="profile_and_memories",
            description="Both relevant profile and relevant memories injected",
            contexts=base_contexts(
                user_profile=RELEVANT_PROFILE,
                relevant_memories=RELEVANT_MEMORIES,
            ),
        ),
        EvalScenario(
            id="irrelevant_profile",
            description="Irrelevant profile — should not distort memory content",
            contexts=base_contexts(user_profile=IRRELEVANT_PROFILE),
        ),
    ]

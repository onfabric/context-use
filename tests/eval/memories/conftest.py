from __future__ import annotations

import pytest

from context_use.batch.grouper import ThreadGroup
from context_use.config import load_config
from context_use.llm.litellm import LiteLLMSyncClient
from context_use.llm.models import OpenAIEmbeddingModel, OpenAIModel

from .scenarios import EvalScenario, make_scenarios

_SCENARIO_IDS = [
    "baseline",
    "relevant_profile",
    "relevant_memories",
    "profile_and_memories",
    "irrelevant_profile",
]


@pytest.fixture(scope="session")
def llm_client() -> LiteLLMSyncClient:
    cfg = load_config()
    if not cfg.openai_api_key:
        pytest.skip("OpenAI API key not configured")
    return LiteLLMSyncClient(
        model=OpenAIModel.GPT_4O,
        api_key=cfg.openai_api_key,
        embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
    )


@pytest.fixture(scope="session", params=_SCENARIO_IDS)
def scenario(
    request: pytest.FixtureRequest,
    conversation_groups: list[ThreadGroup],
) -> EvalScenario:
    scenarios = {s.id: s for s in make_scenarios(conversation_groups)}
    return scenarios[request.param]

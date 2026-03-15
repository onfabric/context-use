from __future__ import annotations

import pytest

from context_use.config import load_config
from context_use.llm.base import PromptItem
from context_use.llm.litellm import LiteLLMSyncClient
from context_use.llm.models import OpenAIEmbeddingModel, OpenAIModel
from context_use.memories.prompt.base import GroupContext
from context_use.memories.prompt.conversation import (
    AgentConversationMemoryPromptBuilder,
)


def pytest_collection_modifyitems(items: list, config) -> None:  # noqa: ANN001
    for item in items:
        item.add_marker(pytest.mark.llm)


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


@pytest.fixture(scope="session")
def prompts(group_contexts: list[GroupContext]) -> list[PromptItem]:
    return AgentConversationMemoryPromptBuilder(group_contexts).build()
